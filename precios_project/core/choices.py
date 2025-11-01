# Tipos de lista de precios
TIPO_LISTA_CHOICES = [
    ('normal', 'Normal'),
    ('promocion', 'Promoción'),
    ('mayoreo', 'Mayoreo'),
]

# Canales de venta
CANAL_CHOICES = [
    ('web', 'Web'),
    ('tienda', 'Tienda'),
    ('distribuidor', 'Distribuidor'),
    ('otro', 'Otro'),
]

# Estados de lista
ESTADO_CHOICES = [
    ('borrador', 'Borrador'),
    ('vigente', 'Vigente'),
    ('inactiva', 'Inactiva'),
]

# Tipos de regla de precio
TIPO_REGLA_CHOICES = [
    ('canal', 'Canal'),
    ('escala_unidades', 'Escala de Unidades'),
    ('escala_monto', 'Escala de Monto'),
    ('combinacion', 'Combinación de Productos'),
    ('monto_pedido', 'Monto de Pedido'),
    ('descuento_proveedor', 'Descuento del Proveedor'),
]
