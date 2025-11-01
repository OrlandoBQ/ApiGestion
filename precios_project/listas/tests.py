from django.test import TestCase, Client
from django.urls import reverse
from rest_framework.test import APIClient
from .models import Empresa, Sucursal, Articulo, ListaPrecio, PrecioArticulo, ReglaPrecio, Orden, LineaOrden, CombinacionProducto
from .services import PrecioService
from django.utils import timezone
from decimal import Decimal
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model


class PrecioAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='tester', password='test1234')
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

        # crear datos mínimos
        self.empresa = Empresa.objects.create(nombre='Empresa Test')
        self.sucursal = Sucursal.objects.create(empresa=self.empresa, nombre='Sucursal Central')
        self.articulo = Articulo.objects.create(codigo='A001', nombre='Artículo 1', ultimo_costo=Decimal('10.00'))

        hoy = timezone.now().date()
        self.lista = ListaPrecio.objects.create(
            empresa=self.empresa,
            sucursal=self.sucursal,
            nombre='Lista Test',
            tipo='normal',
            canal='web',
            fecha_inicio=hoy,
            fecha_fin=hoy.replace(year=hoy.year + 1),
            estado='vigente'
        )
        PrecioArticulo.objects.create(lista=self.lista, articulo=self.articulo, precio_base=Decimal('15.00'))

    def test_calcular_precio_basico(self):
        """Debe devolver el precio base y final igual cuando no hay reglas"""
        payload = {
            'empresa_id': self.empresa.id,
            'sucursal_id': self.sucursal.id,
            'articulo_id': self.articulo.id,
            'canal': 'web',
            'cantidad': 1,
            'monto_pedido': '0.00'
        }
        resp = self.client.post('/api/precio/calcular/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('precio_base', data)
        self.assertEqual(str(data['precio_base']), '15.00')
        self.assertEqual(str(data['precio_final']), '15.00')
        self.assertEqual(data['reglas_aplicadas'], [])

    def test_sin_lista_vigente(self):
        """Debe manejar correctamente la falta de lista vigente"""
        otra_sucursal = Sucursal.objects.create(empresa=self.empresa, nombre='Otra')
        payload = {
            'empresa_id': self.empresa.id,
            'sucursal_id': otra_sucursal.id,
            'articulo_id': self.articulo.id,
            'canal': 'web',
            'cantidad': 1,
            'monto_pedido': '0.00'
        }
        resp = self.client.post('/api/precio/calcular/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('lista_usada') is None or data.get('precio_base') is None)

    def test_regla_escala_unidades_aplica_descuento(self):
        """Debe aplicar descuento cuando la cantidad cumple el rango de la regla"""
        ReglaPrecio.objects.create(
            lista=self.lista,
            tipo='escala_unidades',
            prioridad=1,
            activo=True,
            min_unidades=10,
            max_unidades=100,
            porcentaje_descuento=Decimal('10.00'),
        )
        payload = {
            'empresa_id': self.empresa.id,
            'sucursal_id': self.sucursal.id,
            'articulo_id': self.articulo.id,
            'canal': 'web',
            'cantidad': 20,
            'monto_pedido': '0.00'
        }
        resp = self.client.post('/api/precio/calcular/', payload, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # precio base 15, descuento 10% → 13.50
        self.assertEqual(str(data['precio_final']), '13.50')
        self.assertEqual(len(data['reglas_aplicadas']), 1)

    def test_precio_bajo_costo_no_autorizado(self):
        """Debe marcar como bajo costo no autorizado si precio_base < costo"""
        # Cambiamos el precio base a 8 (menor que 10 de costo)
        p = PrecioArticulo.objects.get(lista=self.lista, articulo=self.articulo)
        p.precio_base = Decimal('8.00')
        p.autorizado_bajo_costo = False
        p.save()
        payload = {
            'empresa_id': self.empresa.id,
            'sucursal_id': self.sucursal.id,
            'articulo_id': self.articulo.id,
            'canal': 'web',
            'cantidad': 1,
            'monto_pedido': '0.00'
        }
        resp = self.client.post('/api/precio/calcular/', payload, format='json')
        data = resp.json()
        self.assertIn('razon_bajo_costo', data)
        self.assertIn('bajo costo', data['razon_bajo_costo'].lower())

    def test_precio_bajo_costo_con_descuento_proveedor(self):
        """Debe aceptar precio bajo costo si hay regla descuento_proveedor"""
        p = PrecioArticulo.objects.get(lista=self.lista, articulo=self.articulo)
        p.precio_base = Decimal('8.00')
        p.save()
        # Regla que reconoce 30% de descuento → precio mínimo permitido = 10 * (1 - 0.3) = 7
        ReglaPrecio.objects.create(
            lista=self.lista,
            tipo='descuento_proveedor',
            prioridad=999,
            activo=True,
            porcentaje_descuento=Decimal('30.00')
        )
        payload = {
            'empresa_id': self.empresa.id,
            'sucursal_id': self.sucursal.id,
            'articulo_id': self.articulo.id,
            'canal': 'web',
            'cantidad': 1,
            'monto_pedido': '0.00'
        }
        resp = self.client.post('/api/precio/calcular/', payload, format='json')
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue('descuento_proveedor' in str(data['reglas_aplicadas']).lower())

class OrdenConfirmTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.e = Empresa.objects.create(nombre='E1')
        self.s = Sucursal.objects.create(empresa=self.e, nombre='S1')
        self.a1 = Articulo.objects.create(codigo='A1', nombre='Art1', ultimo_costo=10)
        self.a2 = Articulo.objects.create(codigo='A2', nombre='Art2', ultimo_costo=5)
        self.lista = ListaPrecio.objects.create(
            empresa=self.e, sucursal=self.s, nombre='Lista', tipo='normal', canal='otro',
            fecha_inicio='2025-01-01', fecha_fin='2026-01-01', estado='vigente'
        )
        PrecioArticulo.objects.create(lista=self.lista, articulo=self.a1, precio_base=20)
        PrecioArticulo.objects.create(lista=self.lista, articulo=self.a2, precio_base=12)
        combo = CombinacionProducto.objects.create(lista=self.lista, nombre='Combo', porcentaje_descuento=10)
        combo.articulos.set([self.a1, self.a2])

        # crear orden
        self.orden = Orden.objects.create(empresa=self.e, sucursal=self.s, canal='otro', total_bruto=32)
        LineaOrden.objects.create(orden=self.orden, articulo=self.a1, cantidad=1, precio_unitario=0)
        LineaOrden.objects.create(orden=self.orden, articulo=self.a2, cantidad=1, precio_unitario=0)

    def test_confirmar_orden_aplica_combinacion(self):
        url = reverse('listas:confirmar_orden', kwargs={'orden_id': self.orden.id})
        resp = self.client.post(url)
        self.orden.refresh_from_db()
        # Después de confirmar, la orden debe estar en 'confirmada'
        self.assertEqual(self.orden.estado, 'confirmada')
        # y líneas deben tener precio_unitario > 0
        for li in self.orden.lineas.all():
            self.assertGreater(li.precio_unitario, Decimal('0.00'))


class CombinacionAplicacionTest(TestCase):
    def setUp(self):
        self.e = Empresa.objects.create(nombre='E')
        self.s = Sucursal.objects.create(empresa=self.e, nombre='S')
        self.a1 = Articulo.objects.create(codigo='A1', nombre='Art1', ultimo_costo=10)
        self.a2 = Articulo.objects.create(codigo='A2', nombre='Art2', ultimo_costo=5)
        self.lista = ListaPrecio.objects.create(empresa=self.e, sucursal=self.s, nombre='L',
                                                tipo='normal', canal='otro',
                                                fecha_inicio='2025-01-01', fecha_fin='2026-01-01', estado='vigente')
        PrecioArticulo.objects.create(lista=self.lista, articulo=self.a1, precio_base=20)
        PrecioArticulo.objects.create(lista=self.lista, articulo=self.a2, precio_base=12)
        combo = CombinacionProducto.objects.create(lista=self.lista, nombre='Combo', porcentaje_descuento=10, tipo_aplicacion='descuento_pct')
        combo.articulos.set([self.a1, self.a2])

        self.orden = Orden.objects.create(empresa=self.e, sucursal=self.s, canal='otro', total_bruto=32)
        LineaOrden.objects.create(orden=self.orden, articulo=self.a1, cantidad=1, precio_unitario=0)
        LineaOrden.objects.create(orden=self.orden, articulo=self.a2, cantidad=1, precio_unitario=0)

    def test_combinacion_aplica_descuento(self):
        carrito = [{'articulo_id': self.a1.id, 'cantidad':1}, {'articulo_id': self.a2.id, 'cantidad':1}]
        res = PrecioService.calcular_precio(
            empresa=self.e,
            sucursal=self.s,
            articulo=self.a1,
            canal='otro',
            cantidad=1,
            monto_pedido=Decimal('32.00'),
            fecha=None,
            carrito_articulos=carrito
        )
        self.assertIsNotNone(res['precio_final'])
        self.assertLess(Decimal(res['precio_final']), Decimal(res['precio_base']))
        # comprobamos que la combinacion fue reportada
        self.assertIsNotNone(res.get('combinacion_aplicada'))