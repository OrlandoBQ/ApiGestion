from django import forms
from .models import ListaPrecio, ReglaPrecio, PrecioArticulo, Articulo, LineaArticulo, GrupoArticulo, Orden, LineaOrden, CombinacionProducto
from django.db import transaction
from django.forms import inlineformset_factory
from django.http import JsonResponse
from .services import PrecioService
from django.shortcuts import get_object_or_404
# ------------------------------
# Formulario para Listas de Precio
# ------------------------------
class ListaPrecioForm(forms.ModelForm):
    class Meta:
        model = ListaPrecio
        fields = ['empresa', 'sucursal', 'nombre', 'tipo', 'canal', 'fecha_inicio', 'fecha_fin', 'estado']
        widgets = {'fecha_inicio': forms.DateInput(attrs={'type':'date'}), 'fecha_fin': forms.DateInput(attrs={'type':'date'})}

    def clean(self):
        cleaned = super().clean()
        # construimos instancia temporal para validar reglas del modelo (clean())
        inst_data = {**(self.instance.__dict__ if self.instance and self.instance.pk else {}), **cleaned}
        # eliminar _state si viene
        inst = ListaPrecio(**{k: v for k, v in inst_data.items() if not k.startswith('_')})
        try:
            inst.full_clean()
        except Exception as e:
            # pasar errores legibles al form
            raise forms.ValidationError(e)
        return cleaned

# ------------------------------
# Formulario para Reglas de Precio
# ------------------------------
class ReglaPrecioForm(forms.ModelForm):
    class Meta:
        model = ReglaPrecio
        fields = [
            'lista', 'tipo', 'prioridad', 'activo', 'porcentaje_descuento',
            'canal', 'min_unidades', 'max_unidades', 'min_monto', 'max_monto',
            'articulo', 'grupo', 'linea'  # si quieres incluir estos campos opcionales
        ]
        widgets = {
            'min_unidades': forms.NumberInput(attrs={'min': 0}),
            'max_unidades': forms.NumberInput(attrs={'min': 0}),
            'min_monto': forms.NumberInput(attrs={'step': '0.01'}),
            'max_monto': forms.NumberInput(attrs={'step': '0.01'}),
        }

    def clean(self):
        cleaned = super().clean()
        lista = cleaned.get('lista') or (self.instance.lista if self.instance else None)
        tipo = cleaned.get('tipo') or (self.instance.tipo if self.instance else None)
        prioridad = cleaned.get('prioridad') or (self.instance.prioridad if self.instance else None)
        canal = cleaned.get('canal') or (self.instance.canal if self.instance else None)

        qs = ReglaPrecio.objects.filter(lista=lista, tipo=tipo).exclude(pk=self.instance.pk if self.instance else None)
        if canal:
            qs = qs.filter(canal=canal)
        if qs.filter(prioridad=prioridad).exists():
            self.add_error('prioridad', 'Ya existe una regla con la misma prioridad para esta lista/tipo/canal.')
        # tu validación previa de min/max ya existe
        return cleaned

# ------------------------------
# Formulario para PrecioArticulo
# ------------------------------
class PrecioArticuloForm(forms.ModelForm):
    class Meta:
        model = PrecioArticulo
        fields = ['lista', 'articulo', 'precio_base', 'autorizado_bajo_costo', 'motivo_bajo_costo']
        widgets = {
            'precio_base': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def clean_precio_base(self):
        precio = self.cleaned_data.get('precio_base')
        articulo = self.cleaned_data.get('articulo')
        autorizado = self.cleaned_data.get('autorizado_bajo_costo')

        if precio is not None and articulo and not autorizado:
            if precio < articulo.ultimo_costo:
                raise forms.ValidationError(
                    f"El precio base no puede ser inferior al último costo registrado ({articulo.ultimo_costo}) sin autorización."
                )
        return precio


# ------------------------------
# Formulario para Artículos
# ------------------------------
class ArticuloForm(forms.ModelForm):
    class Meta:
        model = Articulo
        fields = ['codigo', 'nombre', 'linea', 'grupo', 'ultimo_costo']
        widgets = {
            'ultimo_costo': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def clean_ultimo_costo(self):
        costo = self.cleaned_data.get('ultimo_costo')
        if costo is not None and costo < 0:
            raise forms.ValidationError("El costo no puede ser negativo.")
        return costo

# ------------------------------
# Formulario para Línea de Artículo
# ------------------------------
class LineaArticuloForm(forms.ModelForm):
    class Meta:
        model = LineaArticulo
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la línea'}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        if not nombre:
            raise forms.ValidationError("El nombre de la línea no puede estar vacío.")
        # Evitar duplicados
        if LineaArticulo.objects.filter(nombre__iexact=nombre).exists():
            raise forms.ValidationError("Ya existe una línea con ese nombre.")
        return nombre


# ------------------------------
# Formulario para Grupo de Artículo
# ------------------------------
class GrupoArticuloForm(forms.ModelForm):
    class Meta:
        model = GrupoArticulo
        fields = ['linea', 'nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre del grupo'}),
            'linea': forms.Select(),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        linea = self.cleaned_data.get('linea')
        if not nombre:
            raise forms.ValidationError("El nombre del grupo no puede estar vacío.")
        # Evitar duplicados dentro de la misma línea
        if GrupoArticulo.objects.filter(nombre__iexact=nombre, linea=linea).exists():
            raise forms.ValidationError("Ya existe un grupo con ese nombre en esta línea.")
        return nombre
    
def confirmar_orden(request, orden_id):
    orden = get_object_or_404(Orden, pk=orden_id)
    empresa = orden.empresa
    sucursal = orden.sucursal
    canal = orden.canal
    carrito = [{'articulo_id': li.articulo_id, 'cantidad': li.cantidad} for li in orden.lineas.all()]

    errores = []
    with transaction.atomic():
        for linea in orden.lineas.select_related('articulo'):
            res = PrecioService.calcular_precio(
                empresa=empresa,
                sucursal=sucursal,
                articulo=linea.articulo,
                canal=canal,
                cantidad=linea.cantidad,
                monto_pedido=orden.total_bruto,
                carrito_articulos=carrito
            )
            if res.get('precio_final') is None:
                errores.append(f"{linea.articulo.codigo}: {res.get('razon_bajo_costo')}")
                continue
            if 'bajo costo' in (res.get('razon_bajo_costo') or '') and not res.get('autorizado_bajo_costo'):
                errores.append(f"{linea.articulo.codigo}: precio por debajo del costo sin autorización.")
            linea.precio_unitario = res['precio_final']
            linea.save(update_fields=['precio_unitario'])
        if errores:
            transaction.set_rollback(True)
            return JsonResponse({'ok': False, 'errors': errores}, status=400)
        orden.estado = 'confirmada'
        orden.save()
    return JsonResponse({'ok': True})


class OrdenForm(forms.ModelForm):
    class Meta:
        model = Orden
        fields = ['empresa', 'sucursal', 'canal', 'total_bruto', 'estado']
        widgets = {
            'total_bruto': forms.NumberInput(attrs={'step':'0.01'}),
        }

class LineaOrdenForm(forms.ModelForm):
    class Meta:
        model = LineaOrden
        fields = ['articulo', 'cantidad', 'precio_unitario']
        widgets = {
            'cantidad': forms.NumberInput(attrs={'min':1}),
            'precio_unitario': forms.NumberInput(attrs={'step':'0.01'}),
        }

# Inline formset: Orden -> LineaOrden
LineaOrdenFormSet = inlineformset_factory(
    Orden,
    LineaOrden,
    form=LineaOrdenForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True
)

class CombinacionProductoForm(forms.ModelForm):
    # Campo extra opcional (no se guarda en la BD)
    precio_fijo = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )

    class Meta:
        model = CombinacionProducto
        fields = ['lista', 'nombre', 'articulos']  # solo campos válidos del modelo
        widgets = {
            'articulos': forms.SelectMultiple(attrs={'size': 10}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        lista = self.cleaned_data.get('lista')
        if CombinacionProducto.objects.filter(nombre__iexact=nombre, lista=lista).exists():
            raise forms.ValidationError("Ya existe una combinación con ese nombre en esta lista.")
        return nombre

    def clean_precio_fijo(self):
        precio = self.cleaned_data.get('precio_fijo')
        if precio is not None and precio < 0:
            raise forms.ValidationError("El precio fijo no puede ser negativo.")
        return precio

    def clean(self):
        cleaned = super().clean()
        articulos = cleaned.get('articulos')
        if articulos and len(articulos) < 2:
            raise forms.ValidationError("Una combinación debe incluir al menos 2 artículos.")
        return cleaned