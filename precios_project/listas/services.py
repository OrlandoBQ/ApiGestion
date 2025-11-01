# listas/services.py
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Optional, Dict, Any, List
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from typing import Optional, Dict, Any, List
from .models import (
    Empresa, Sucursal, Articulo, ListaPrecio, PrecioArticulo,
    ReglaPrecio, CombinacionProducto
)

# Ajuste de precisión (suficiente para precios en monedas con 2 decimales)
getcontext().prec = 28
CENTS = Decimal('0.01')


class PrecioService:
    """
    Servicio para obtener listas vigentes y calcular precios aplicando reglas.
    Métodos principales:
      - obtener_lista_vigente(empresa, sucursal, canal, fecha)
      - calcular_precio(empresa, sucursal, articulo, canal, cantidad, monto_pedido, fecha)
      - aplicar_reglas(lista, articulo, canal, cantidad, monto_pedido)
      - validar_costo(precio_articulo, articulo)
      - registrar_descuento_proveedor(precio_articulo, porcentaje_reconocido, autorizado_por)
    """

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        """Normaliza a 2 decimales."""
        return (value.quantize(CENTS, rounding=ROUND_HALF_UP))

    @staticmethod
    def obtener_lista_vigente(empresa: Empresa,
                              sucursal: Sucursal,
                              canal: Optional[str] = None,
                              fecha: Optional[Any] = None) -> Optional[ListaPrecio]:
        """
        Busca la lista vigente para la empresa/sucursal y opcionalmente por canal.
        Prioridades:
          1) lista con estado 'vigente' y fecha actual entre inicio/fin y canal exacto
          2) lista 'vigente' sin canal específico
          3) None si no hay lista.
        """
        if fecha is None:
            fecha = timezone.now().date()

        qs = ListaPrecio.objects.filter(
            empresa=empresa,
            sucursal=sucursal,
            estado='vigente',
            fecha_inicio__lte=fecha,
            fecha_fin__gte=fecha
        )

        # Preferir listas con el canal específico (si se pasa)
        if canal:
            qs_canal = qs.filter(canal=canal)
            if qs_canal.exists():
                # si hay múltiples, elegimos la más reciente por fecha_inicio
                return qs_canal.order_by('-fecha_inicio').first()
        # fallback a cualquier canal
        if qs.exists():
            return qs.order_by('-fecha_inicio').first()
        return None

    @staticmethod
    def calcular_precio(empresa: Empresa,
                        sucursal: Sucursal,
                        articulo: Articulo,
                        canal: Optional[str] = None,
                        cantidad: int = 1,
                        monto_pedido: Optional[Decimal] = None,
                        fecha: Optional[Any] = None,
                        carrito_articulos: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Calcula el precio para un artículo. Retorna dict con:
        - precio_base
        - precio_final
        - lista_usada (id y nombre si aplica)
        - reglas_aplicadas: lista de dicts {regla_id, descripcion, tipo, porcentaje_descuento, ...}
        - autorizado_bajo_costo (bool)
        - razon_bajo_costo (si aplica)
        - combinacion_aplicada (id si aplica)
        """
        if fecha is None:
            fecha = timezone.now().date()
        if monto_pedido is None:
            monto_pedido = Decimal('0.00')
        else:
            monto_pedido = Decimal(monto_pedido)

        result: Dict[str, Any] = {
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

        # Validar costo (si está por debajo del costo y no autorizado, marcar)
        try:
            PrecioService.validar_costo(precio_articulo, articulo)
        except ValueError as e:
            result['autorizado_bajo_costo'] = False
            result['razon_bajo_costo'] = str(e)
            # seguimos calculando (solo advertencia)

        # Aplicar reglas (ahora aceptando carrito_articulos para evaluar combinaciones)
        reglas_aplicadas = PrecioService.aplicar_reglas(
            lista=lista,
            articulo=articulo,
            canal=canal,
            cantidad=cantidad,
            monto_pedido=monto_pedido,
            carrito_articulos=carrito_articulos
        )
        result['reglas_aplicadas'] = reglas_aplicadas

        # Calculo del precio final: aplicar descuentos secuencialmente sobre el precio base
        precio = precio_base
        detalle_descuento_total = Decimal('0.00')
        # Si hay una combinación que define 'precio_fijo' queremos que reemplace el precio directamente.
        # Buscamos primero si alguna regla aplicada indica 'accion':'precio_fijo'
        precio_fijo_aplicado = False
        for r in reglas_aplicadas:
            if r.get('tipo') == 'combinacion' and r.get('accion') == 'precio_fijo':
                # 'valor' contiene el precio objetivo (string), convertimos a Decimal
                try:
                    precio = Decimal(r.get('valor'))
                    precio = PrecioService._quantize(precio)
                    result['combinacion_aplicada'] = r.get('combo_id') or r.get('regla_id')
                    precio_fijo_aplicado = True
                    # Si se aplica precio fijo dejamos ese precio y no aplicamos más descuentos sobre él
                    break
                except Exception:
                    # si falla la conversión, ignoramos y seguimos con descuentos por pct si hubiera
                    precio_fijo_aplicado = False

        if not precio_fijo_aplicado:
            # Aplicar secuencialmente todos los descuentos por porcentaje
            for r in reglas_aplicadas:
                pct = Decimal(r.get('porcentaje_descuento', '0')) / Decimal('100')
                if pct == 0:
                    continue
                descuento = (precio * pct).quantize(CENTS, rounding=ROUND_HALF_UP)
                precio = (precio - descuento).quantize(CENTS, rounding=ROUND_HALF_UP)
                detalle_descuento_total += descuento
                # si la regla es de tipo combinacion y tiene combo_id, registrarlo como aplicada
                if r.get('tipo') == 'combinacion' and r.get('combo_id'):
                    result['combinacion_aplicada'] = r.get('combo_id')

        result['precio_final'] = PrecioService._quantize(precio)
        result['descuento_total'] = PrecioService._quantize(detalle_descuento_total)

        # Si el precio final está bajo costo y el precio_articulo está marcado autorizado -> reflejarlo
        if result['precio_final'] < Decimal(articulo.ultimo_costo):
            result['autorizado_bajo_costo'] = bool(precio_articulo.autorizado_bajo_costo)
            if result['autorizado_bajo_costo']:
                result['razon_bajo_costo'] = precio_articulo.motivo_bajo_costo or "Autorizado manualmente (bajo costo)"
            else:
                # intentar ver si existe regla de tipo 'descuento_proveedor' que reconozca
                dp_rules = ReglaPrecio.objects.filter(lista=lista, tipo='descuento_proveedor', activo=True)
                if dp_rules.exists():
                    result['razon_bajo_costo'] = 'Bajo costo sin autorización explícita; existe regla de reconocimiento de proveedor'
                else:
                    result['razon_bajo_costo'] = 'Precio final inferior al último costo y no autorizado (bajo costo)'

        return result

    @staticmethod
    def aplicar_reglas(lista: ListaPrecio,
                       articulo: Articulo,
                       canal: Optional[str],
                       cantidad: int,
                       monto_pedido: Decimal,
                       carrito_articulos: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        Evalúa las reglas activas de la lista en orden de prioridad.
        Devuelve una lista de reglas aplicadas con su efecto:
        [
          {
            'regla_id': ...,
            'tipo': ...,
            'descripcion': ...,
            'porcentaje_descuento': ...,
            'accion': ...,
            'valor': ...,
            'combo_id': ...
          }
        ]
        Tipos soportados:
          - canal
          - escala_unidades
          - escala_monto
          - monto_pedido
          - combinacion (usa carrito_articulos)
          - descuento_proveedor
        """
        aplicado: List[Dict[str, Any]] = []
        reglas = ReglaPrecio.objects.filter(lista=lista, activo=True).order_by('prioridad')

        for regla in reglas:
            aplica = False

            # canal
            if regla.tipo == 'canal':
                if regla.canal and canal and regla.canal == canal:
                    aplica = True

            # escala unidades
            elif regla.tipo == 'escala_unidades':
                if regla.min_unidades and regla.max_unidades:
                    if regla.min_unidades <= cantidad <= regla.max_unidades:
                        aplica = True
                elif regla.min_unidades and cantidad >= regla.min_unidades:
                    aplica = True

            # escala monto
            elif regla.tipo == 'escala_monto':
                if regla.min_monto and regla.max_monto:
                    if regla.min_monto <= monto_pedido <= regla.max_monto:
                        aplica = True
                elif regla.min_monto and monto_pedido >= regla.min_monto:
                    aplica = True

            # monto pedido (genérica)
            elif regla.tipo == 'monto_pedido':
                if regla.min_monto and monto_pedido >= regla.min_monto:
                    aplica = True

            # combinacion — se evalúa según carrito_articulos
            elif regla.tipo == 'combinacion':
                combos = CombinacionProducto.objects.filter(lista=lista, activo=True)
                for combo in combos:
                    articulos_combo = list(combo.articulos.values_list('id', flat=True))
                    if articulo.id not in articulos_combo:
                        continue

                    # Verificar si todos los artículos de la combinación están presentes en el carrito
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
                            break  # una combinación aplicada basta

            # descuento_proveedor
            elif regla.tipo == 'descuento_proveedor':
                aplica = True

            # Reglas estándar (no combinaciones)
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
    def validar_costo(precio_articulo: PrecioArticulo, articulo: Articulo) -> bool:
        """
        Valida que el precio_base no sea inferior al último costo, salvo que:
         - precio_articulo.autorizado_bajo_costo == True
         - O exista regla descuento_proveedor en la lista que permita rango reconocido
        Si no cumple, levanta ValueError con mensaje que incluye 'bajo costo'.
        """
        precio = Decimal(precio_articulo.precio_base)
        costo = Decimal(articulo.ultimo_costo)

        if precio >= costo:
            return True

        # si está marcado como autorizado, ok
        if precio_articulo.autorizado_bajo_costo:
            return True

        # buscar reglas tipo 'descuento_proveedor' para la lista (si existen, se permiten ciertos rangos)
        reglas_dp = ReglaPrecio.objects.filter(lista=precio_articulo.lista, tipo='descuento_proveedor', activo=True)
        if reglas_dp.exists():
            # Interpreto que la regla contiene porcentaje_descuento reconocido por proveedor.
            for r in reglas_dp:
                pct = (Decimal(r.porcentaje_descuento) / Decimal('100')) if r.porcentaje_descuento else Decimal('0')
                # precio mínimo permitido según reconocimiento: costo * (1 - pct_reconocido)
                precio_min_permitido = (costo * (Decimal('1') - pct)).quantize(CENTS, rounding=ROUND_HALF_UP)
                if precio >= precio_min_permitido:
                    return True
            # si ninguna regla autoriza el precio actual, no está validado
            raise ValueError('Precio por debajo del último costo (bajo costo) sin reconocimiento suficiente del proveedor.')
        # si no hay reglas ni autorización, error
        raise ValueError('Precio por debajo del último costo (bajo costo) y no autorizado.')


    @staticmethod
    @transaction.atomic
    def registrar_descuento_proveedor(precio_articulo: PrecioArticulo,
                                      porcentaje_reconocido: Decimal,
                                      autorizado_por) -> PrecioArticulo:
        """
        Marca el precio_articulo como autorizado por reconocimiento del proveedor.
        """
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
        precio_articulo.motivo_bajo_costo = f"Autorizado por reconocimiento proveedor {porcentaje_reconocido}% por {getattr(autorizado_por, 'username', str(autorizado_por))}"
        precio_articulo.save(update_fields=['autorizado_bajo_costo', 'motivo_bajo_costo', 'actualizado_en'])

        return precio_articulo
