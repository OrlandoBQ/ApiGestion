# listas/serializers.py
from rest_framework import serializers
from decimal import Decimal
from .models import Empresa, Sucursal, Articulo, LineaArticulo, GrupoArticulo, ListaPrecio, PrecioArticulo, ReglaPrecio, CombinacionProducto

class PrecioConsultaSerializer(serializers.Serializer):
    empresa_id = serializers.IntegerField()
    sucursal_id = serializers.IntegerField()
    articulo_id = serializers.IntegerField()
    canal = serializers.CharField(required=False, allow_blank=True, default=None)
    cantidad = serializers.IntegerField(required=False, default=1, min_value=1)
    monto_pedido = serializers.DecimalField(required=False, max_digits=12, decimal_places=2, default=Decimal('0.00'))
    fecha = serializers.DateField(required=False, allow_null=True)

class ReglaAplicadaSerializer(serializers.Serializer):
    regla_id = serializers.IntegerField()
    tipo = serializers.CharField()
    descripcion = serializers.CharField()
    porcentaje_descuento = serializers.CharField()

class PrecioResultadoSerializer(serializers.Serializer):
    precio_base = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    precio_final = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    descuento_total = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    lista_usada = serializers.DictField(child=serializers.CharField(), required=False, allow_null=True)
    reglas_aplicadas = ReglaAplicadaSerializer(many=True)
    autorizado_bajo_costo = serializers.BooleanField()
    razon_bajo_costo = serializers.CharField(allow_null=True, allow_blank=True, required=False)

# --- Entidades básicas ---
class EmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Empresa
        fields = ['id', 'nombre', 'ruc']

class SucursalSerializer(serializers.ModelSerializer):
    empresa = EmpresaSerializer(read_only=True)
    empresa_id = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), source='empresa', write_only=True)
    class Meta:
        model = Sucursal
        fields = ['id', 'nombre', 'direccion', 'empresa', 'empresa_id']

class ArticuloSerializer(serializers.ModelSerializer):
    class Meta:
        model = Articulo
        fields = ['id', 'codigo', 'nombre', 'ultimo_costo', 'linea', 'grupo']

# --- ListaPrecio CRUD ---
class ListaPrecioSerializer(serializers.ModelSerializer):
    empresa = EmpresaSerializer(read_only=True)
    empresa_id = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), source='empresa', write_only=True)
    sucursal = SucursalSerializer(read_only=True)
    sucursal_id = serializers.PrimaryKeyRelatedField(queryset=Sucursal.objects.all(), source='sucursal', write_only=True)

    class Meta:
        model = ListaPrecio
        fields = [
            'id', 'nombre', 'empresa', 'empresa_id', 'sucursal', 'sucursal_id',
            'tipo', 'canal', 'fecha_inicio', 'fecha_fin', 'estado', 'creado_por', 'creado_en'
        ]
        read_only_fields = ['creado_por', 'creado_en']

    def validate(self, data):
        # delegar validaciones de dominio al modelo: fecha_fin >= fecha_inicio, solapamiento, etc.
        # Creamos instancia temporal para validar clean()
        inst = ListaPrecio(**{**(self.instance.__dict__ if self.instance else {}), **data})
        # eliminar atributos internos
        if hasattr(inst, '_state'):
            inst._state = getattr(inst, '_state')
        try:
            inst.full_clean()
        except Exception as e:
            raise serializers.ValidationError(e)
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            validated_data['creado_por'] = request.user
        instance = super().create(validated_data)
        return instance

# --- PrecioArticulo CRUD ---
class PrecioArticuloSerializer(serializers.ModelSerializer):
    lista = ListaPrecioSerializer(read_only=True)
    lista_id = serializers.PrimaryKeyRelatedField(queryset=ListaPrecio.objects.all(), source='lista', write_only=True)
    articulo = ArticuloSerializer(read_only=True)
    articulo_id = serializers.PrimaryKeyRelatedField(queryset=Articulo.objects.all(), source='articulo', write_only=True)

    class Meta:
        model = PrecioArticulo
        fields = ['id', 'lista', 'lista_id', 'articulo', 'articulo_id',
                  'precio_base', 'autorizado_bajo_costo', 'motivo_bajo_costo', 'actualizado_en']

    def validate(self, data):
        # validación ligera y delegar la validación de negocio a full_clean
        inst = PrecioArticulo(**{**(self.instance.__dict__ if self.instance else {}), **data})
        try:
            inst.full_clean()
        except Exception as e:
            raise serializers.ValidationError(e)
        return data

# --- ReglaPrecio CRUD ---
class ReglaPrecioSerializer(serializers.ModelSerializer):
    lista = ListaPrecioSerializer(read_only=True)
    lista_id = serializers.PrimaryKeyRelatedField(queryset=ListaPrecio.objects.all(), source='lista', write_only=True)

    class Meta:
        model = ReglaPrecio
        fields = [
            'id', 'lista', 'lista_id', 'tipo', 'prioridad', 'activo', 'canal',
            'min_unidades', 'max_unidades', 'min_monto', 'max_monto',
            'porcentaje_descuento', 'articulo', 'grupo', 'linea'
        ]

    def validate(self, data):
        # se podría añadir validaciones adicionales por tipo
        return data

# --- CombinacionProducto CRUD ---
class CombinacionProductoSerializer(serializers.ModelSerializer):
    lista = ListaPrecioSerializer(read_only=True)
    lista_id = serializers.PrimaryKeyRelatedField(queryset=ListaPrecio.objects.all(), source='lista', write_only=True)
    articulos = serializers.PrimaryKeyRelatedField(queryset=Articulo.objects.all(), many=True)

    class Meta:
        model = CombinacionProducto
        fields = ['id', 'lista', 'lista_id', 'nombre', 'articulos', 'porcentaje_descuento', 'minimo_por_articulo', 'tipo_aplicacion', 'activo']

    def validate(self, data):
        articulos = data.get('articulos') or []
        # si es creación: articulos viene en validated_data
        if not self.instance and len(articulos) < 2:
            raise serializers.ValidationError('La combinación debe contener al menos 2 artículos.')

        # si es actualización y articulos no está en data, no hacemos la comprobación aquí
        return data

    def create(self, validated_data):
        articulos = validated_data.pop('articulos', [])
        combo = super().create(validated_data)
        if articulos:
            combo.articulos.set(articulos)
        # validación final: ahora que m2m está seteado, podemos asegurar conteo
        if combo.articulos.count() < 2:
            raise serializers.ValidationError('La combinación debe contener al menos 2 artículos.')
        return combo

    def update(self, instance, validated_data):
        articulos = validated_data.pop('articulos', None)
        instance = super().update(instance, validated_data)
        if articulos is not None:
            instance.articulos.set(articulos)
            if instance.articulos.count() < 2:
                raise serializers.ValidationError('La combinación debe contener al menos 2 artículos.')
        return instance


