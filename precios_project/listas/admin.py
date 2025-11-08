from django.contrib import admin

# Register your models here.
from .models import Empresa, Sucursal, Articulo, GrupoArticulo, LineaArticulo, DetalleOrdenCompraCliente, ListaPrecio, PrecioArticulo, ReglaPrecio, CombinacionProducto

admin.site.register(Empresa)
admin.site.register(Sucursal)
admin.site.register(LineaArticulo)
admin.site.register(GrupoArticulo)
admin.site.register(Articulo)
admin.site.register(DetalleOrdenCompraCliente)
admin.site.register(ListaPrecio)
admin.site.register(PrecioArticulo)
admin.site.register(ReglaPrecio)
admin.site.register(CombinacionProducto)

