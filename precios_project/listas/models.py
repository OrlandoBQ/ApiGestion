from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from core.choices import TIPO_LISTA_CHOICES, CANAL_CHOICES, ESTADO_CHOICES, TIPO_REGLA_CHOICES
User = get_user_model()


# --- Modelos base ---
class Empresa(models.Model):
    nombre = models.CharField(max_length=200)
    ruc = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.nombre


class Sucursal(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='sucursales')
    nombre = models.CharField(max_length=200)
    direccion = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return f"{self.nombre} - {self.empresa.nombre}"


class LineaArticulo(models.Model):
    nombre = models.CharField(max_length=200)

    def __str__(self):
        return self.nombre


class GrupoArticulo(models.Model):
    linea = models.ForeignKey(LineaArticulo, on_delete=models.SET_NULL, null=True, blank=True)
    nombre = models.CharField(max_length=200)

    def __str__(self):
        return self.nombre


class Articulo(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=300)
    linea = models.ForeignKey(LineaArticulo, on_delete=models.SET_NULL, null=True, blank=True)
    grupo = models.ForeignKey(GrupoArticulo, on_delete=models.SET_NULL, null=True, blank=True)
    ultimo_costo = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class DetalleOrdenCompraCliente(models.Model):
    orden_id = models.CharField(max_length=100)
    articulo = models.ForeignKey(Articulo, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    fecha = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.orden_id} - {self.articulo.codigo}"


# --- Modelos del módulo de listas de precio ---
class ListaPrecio(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='listas')
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='listas')
    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=50, choices=TIPO_LISTA_CHOICES, default='normal')
    canal = models.CharField(max_length=50, choices=CANAL_CHOICES, default='otro')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default='borrador')
    creado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha_inicio']
        unique_together = ('empresa', 'sucursal', 'nombre', 'fecha_inicio')

    def clean(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValidationError("La fecha_fin no puede ser anterior a fecha_inicio.")
        overlapping = ListaPrecio.objects.filter(
            empresa=self.empresa, sucursal=self.sucursal
        ).exclude(pk=self.pk).filter(
            fecha_inicio__lte=self.fecha_fin, fecha_fin__gte=self.fecha_inicio
        )
        if overlapping.exists():
            raise ValidationError("Existe otra lista con vigencia que se solapa para la misma empresa/sucursal.")

    def __str__(self):
        return f"{self.nombre} ({self.empresa} - {self.sucursal})"


class PrecioArticulo(models.Model):
    lista = models.ForeignKey(ListaPrecio, on_delete=models.CASCADE, related_name='precios_articulo')
    articulo = models.ForeignKey(Articulo, on_delete=models.CASCADE, related_name='precios')
    precio_base = models.DecimalField(max_digits=12, decimal_places=2)
    autorizado_bajo_costo = models.BooleanField(default=False)
    motivo_bajo_costo = models.TextField(blank=True, null=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('lista', 'articulo')

    def clean(self):
        # Solo compara si precio_base no es None
        if self.precio_base is not None and self.articulo and not self.autorizado_bajo_costo:
            if self.precio_base < self.articulo.ultimo_costo:
                raise ValidationError("El precio base no puede ser inferior al último costo registrado sin autorización.")


class ReglaPrecio(models.Model):
    lista = models.ForeignKey(ListaPrecio, on_delete=models.CASCADE, related_name='reglas')
    tipo = models.CharField(max_length=50, choices=TIPO_REGLA_CHOICES)
    prioridad = models.PositiveIntegerField(default=100)  # menor = mayor prioridad
    activo = models.BooleanField(default=True)

    canal = models.CharField(max_length=50, choices=CANAL_CHOICES, blank=True, null=True)
    min_unidades = models.PositiveIntegerField(blank=True, null=True)
    max_unidades = models.PositiveIntegerField(blank=True, null=True)
    min_monto = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    max_monto = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    porcentaje_descuento = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    articulo = models.ForeignKey(Articulo, on_delete=models.SET_NULL, null=True, blank=True)
    grupo = models.ForeignKey(GrupoArticulo, on_delete=models.SET_NULL, null=True, blank=True)
    linea = models.ForeignKey(LineaArticulo, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['prioridad']
        unique_together = ('lista', 'tipo', 'prioridad', 'canal')

    def clean(self):
        dup = ReglaPrecio.objects.filter(lista=self.lista, tipo=self.tipo).exclude(pk=self.pk)
        if self.canal:
            dup = dup.filter(canal=self.canal)
        if dup.exists():
            pass

    def __str__(self):
        return f"{self.get_tipo_display()} [{self.lista.nombre}] prio:{self.prioridad}"


class CombinacionProducto(models.Model):
    TIPO_APLICACION_CHOICES = (
        ('descuento_pct', 'Descuento %'),
        ('precio_fijo', 'Precio fijo por artículo'),
    )

    lista = models.ForeignKey(ListaPrecio, on_delete=models.CASCADE, related_name='combinaciones')
    nombre = models.CharField(max_length=200)
    articulos = models.ManyToManyField(Articulo, related_name='combinaciones')
    porcentaje_descuento = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    minimo_por_articulo = models.PositiveIntegerField(default=1, help_text="Cantidad mínima por cada artículo de la combinación")
    tipo_aplicacion = models.CharField(max_length=20, choices=TIPO_APLICACION_CHOICES, default='descuento_pct')
    activo = models.BooleanField(default=True)

    def clean(self):
        # Atención: en create/update la relación M2M no está disponible en clean() hasta después de save().
        # Por tanto, comprobación explícita de >1 artículo se hace en el serializer o en un post_save signal.
        pass

    def __str__(self):
        return f"{self.nombre} ({self.lista.nombre})"


class Orden(models.Model):
    ESTADOS = [
        ('borrador', 'Borrador'),
        ('confirmada', 'Confirmada'),
        ('anulada', 'Anulada'),
    ]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE)
    canal = models.CharField(max_length=20, blank=True, null=True)
    total_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='borrador')
    fecha = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Orden {self.id} ({self.get_estado_display()})"


class LineaOrden(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE, related_name='lineas')
    articulo = models.ForeignKey(Articulo, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def subtotal(self):
        return self.cantidad * self.precio_unitario