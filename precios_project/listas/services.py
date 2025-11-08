# listas/services.py
from decimal import Decimal, ROUND_HALF_UP, getcontext
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from .models import (
    Empresa, Sucursal, Articulo, ListaPrecio, PrecioArticulo,
    ReglaPrecio, CombinacionProducto
)

getcontext().prec = 28
CENTS = Decimal('0.01')


class PrecioService:
    """
    Servicio para obtener listas vigentes y calcular precios aplicando reglas.
    """

    @staticmethod
    def _quantize(value):
        """Normaliza a 2 decimales."""
        return value.quantize(CENTS, rounding=ROUND_HALF_UP)

    @staticmethod
    def obtener_lista_vigente(empresa, sucursal, canal=None, fecha=None):
        """Busca la lista vigente para la empresa/sucursal y canal (si aplica)."""
        if fecha is None:
            fecha = timezone.now().date()

        qs = ListaPrecio.objects.filter(
            empresa=empresa,
            sucursal=sucursal,
            estado='vigente',
            fecha_inicio__lte=fecha,
            fecha_fin__gte=fecha
        )

        if canal:
            qs_canal = qs.filter(canal=canal)
            if qs_canal.exists():
                return qs_canal.order_by('-fecha_inicio').first()

        if qs.exists():
            return qs.order_by('-fecha_inicio').first()

        return None

    @staticmethod
    def calcular_precio(empresa, sucursal, articulo, canal=None,
                        cantidad=1, monto_pedido=None, fecha=None,
                        carrito_articulos=None):
        """Calcula el precio de un artículo aplicando reglas."""
        if fecha is None:
            fecha = timezone.now().date()
        if monto_pedido is None:
            monto_pedido = Decimal('0.00')
        else:
            monto_pedido = Decimal(monto_pedido)

        result = {
            'precio_base': None,
            'precio_final': None,
            'lista_usada': None,
            'reglas_aplicadas': [],
            'autorizado_bajo_costo': False,
            'razon_bajo_costo': None,
            'descuento_total': Decimal('0.00'),
            'combinacion_aplicada': None,
        }

        lista = PrecioService.obtener_lista_vigente(empresa, sucursal, canal, fecha)
        if not lista:
            result['razon_bajo_costo'] = 'No existe lista vigente'
            return result

        result['lista_usada'] = {'id': lista.id, 'nombre': lista.nombre, 'canal': lista.canal}

        try:
            precio_articulo = PrecioArticulo.objects.get(lista=lista, articulo=articulo)
        except PrecioArticulo.DoesNotExist:
            result['razon_bajo_costo'] = 'Artículo no tiene precio en la lista'
            return result

        precio_base = Decimal(precio_articulo.precio_base)
        precio_base = PrecioService._quantize(precio_base)
        result['precio_base'] = precio_base

        try:
            PrecioService.validar_costo(precio_articulo, articulo)
        except ValueError as e:
            result['autorizado_bajo_costo'] = False
            result['razon_bajo_costo'] = str(e)

        reglas_aplicadas = PrecioService.aplicar_reglas(
            lista=lista,
            articulo=articulo,
            canal=canal,
            cantidad=cantidad,
            monto_pedido=monto_pedido,
            carrito_articulos=carrito_articulos
        )
        result['reglas_aplicadas'] = reglas_aplicadas

        precio = precio_base
        detalle_descuento_total = Decimal('0.00')
        precio_fijo_aplicado = False

        for r in reglas_aplicadas:
            if r.get('tipo') == 'combinacion' and r.get('accion') == 'precio_fijo':
                try:
                    precio = Decimal(r.get('valor'))
                    precio = PrecioService._quantize(precio)
                    result['combinacion_aplicada'] = r.get('combo_id') or r.get('regla_id')
                    precio_fijo_aplicado = True
                    break
                except Exception:
                    precio_fijo_aplicado = False

        if not precio_fijo_aplicado:
            for r in reglas_aplicadas:
                pct = Decimal(r.get('porcentaje_descuento', '0')) / Decimal('100')
                if pct == 0:
                    continue
                descuento = (precio * pct).quantize(CENTS, rounding=ROUND_HALF_UP)
                precio = (precio - descuento).quantize(CENTS, rounding=ROUND_HALF_UP)
                detalle_descuento_total += descuento
                if r.get('tipo') == 'combinacion' and r.get('combo_id'):
                    result['combinacion_aplicada'] = r.get('combo_id')

        result['precio_final'] = PrecioService._quantize(precio)
        result['descuento_total'] = PrecioService._quantize(detalle_descuento_total)

        if result['precio_final'] < Decimal(articulo.ultimo_costo):
            result['autorizado_bajo_costo'] = bool(precio_articulo.autorizado_bajo_costo)
            if result['autorizado_bajo_costo']:
                result['razon_bajo_costo'] = precio_articulo.motivo_bajo_costo or "Autorizado manualmente (bajo costo)"
            else:
                dp_rules = ReglaPrecio.objects.filter(lista=lista, tipo='descuento_proveedor', activo=True)
                if dp_rules.exists():
                    result['razon_bajo_costo'] = 'Bajo costo sin autorización explícita; existe regla de reconocimiento de proveedor'
                else:
                    result['razon_bajo_costo'] = 'Precio final inferior al último costo y no autorizado (bajo costo)'

        return result

    @staticmethod
    def aplicar_reglas(lista, articulo, canal, cantidad, monto_pedido, carrito_articulos=None):
        """Evalúa las reglas activas de la lista en orden de prioridad."""
        aplicado = []
        reglas = ReglaPrecio.objects.filter(lista=lista, activo=True).order_by('prioridad')

        for regla in reglas:
            aplica = False

            if regla.tipo == 'canal':
                if regla.canal and canal and regla.canal == canal:
                    aplica = True

            elif regla.tipo == 'escala_unidades':
                if regla.min_unidades and regla.max_unidades:
                    if regla.min_unidades <= cantidad <= regla.max_unidades:
                        aplica = True
                elif regla.min_unidades and cantidad >= regla.min_unidades:
                    aplica = True

            elif regla.tipo == 'escala_monto':
                if regla.min_monto and regla.max_monto:
                    if regla.min_monto <= monto_pedido <= regla.max_monto:
                        aplica = True
                elif regla.min_monto and monto_pedido >= regla.min_monto:
                    aplica = True

            elif regla.tipo == 'monto_pedido':
                if regla.min_monto and monto_pedido >= regla.min_monto:
                    aplica = True

            elif regla.tipo == 'combinacion':
                combos = CombinacionProducto.objects.filter(lista=lista, activo=True)
                for combo in combos:
                    articulos_combo = list(combo.articulos.values_list('id', flat=True))
                    if articulo.id not in articulos_combo:
                        continue
                    if carrito_articulos:
                        carrito_ids = [int(a.get('articulo_id')) for a in carrito_articulos]
                        if all(aid in carrito_ids for aid in articulos_combo):
                            aplica = True
                            aplicado.append({
                                'regla_id': regla.id,
                                'tipo': 'combinacion',
                                'descripcion': f'Combinación #{combo.id} - {combo.nombre or "sin nombre"}',
                                'porcentaje_descuento': str(combo.descuento_pct or '0'),
                                'accion': 'precio_fijo' if combo.precio_fijo else 'descuento_pct',
                                'valor': str(combo.precio_fijo or combo.descuento_pct or '0'),
                                'combo_id': combo.id
                            })
                            break

            elif regla.tipo == 'descuento_proveedor':
                aplica = True

            if aplica and regla.tipo != 'combinacion':
                aplicado.append({
                    'regla_id': regla.id,
                    'tipo': regla.tipo,
                    'descripcion': f'Regla {regla.tipo} prio {regla.prioridad}',
                    'porcentaje_descuento': str(regla.porcentaje_descuento or '0'),
                    'accion': 'descuento_pct',
                    'valor': str(regla.porcentaje_descuento or '0'),
                    'combo_id': None
                })

        return aplicado

    @staticmethod
    def validar_costo(precio_articulo, articulo):
        """Valida que el precio_base no sea inferior al costo salvo reglas."""
        precio = Decimal(precio_articulo.precio_base)
        costo = Decimal(articulo.ultimo_costo)

        if precio >= costo:
            return True

        if precio_articulo.autorizado_bajo_costo:
            return True

        reglas_dp = ReglaPrecio.objects.filter(lista=precio_articulo.lista, tipo='descuento_proveedor', activo=True)
        if reglas_dp.exists():
            for r in reglas_dp:
                pct = (Decimal(r.porcentaje_descuento) / Decimal('100')) if r.porcentaje_descuento else Decimal('0')
                precio_min_permitido = (costo * (Decimal('1') - pct)).quantize(CENTS, rounding=ROUND_HALF_UP)
                if precio >= precio_min_permitido:
                    return True
            raise ValueError('Precio por debajo del último costo (bajo costo) sin reconocimiento suficiente del proveedor.')
        raise ValueError('Precio por debajo del último costo (bajo costo) y no autorizado.')

    @staticmethod
    @transaction.atomic
    def registrar_descuento_proveedor(precio_articulo, porcentaje_reconocido, autorizado_por):
        """Marca el precio_articulo como autorizado por reconocimiento del proveedor."""
        regla, created = ReglaPrecio.objects.get_or_create(
            lista=precio_articulo.lista,
            tipo='descuento_proveedor',
            defaults={'prioridad': 999, 'activo': True, 'porcentaje_descuento': porcentaje_reconocido}
        )
        if not created:
            regla.porcentaje_descuento = porcentaje_reconocido
            regla.activo = True
            regla.save()

        precio_articulo.autorizado_bajo_costo = True
        precio_articulo.motivo_bajo_costo = (
            f"Autorizado por reconocimiento proveedor {porcentaje_reconocido}% "
            f"por {getattr(autorizado_por, 'username', str(autorizado_por))}"
        )
        precio_articulo.save(update_fields=['autorizado_bajo_costo', 'motivo_bajo_costo', 'actualizado_en'])

        return precio_articulo
