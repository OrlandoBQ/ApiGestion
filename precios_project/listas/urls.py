from django.urls import path, include
from rest_framework import routers
from . import views

app_name = 'listas'

router = routers.DefaultRouter()
router.register(r'listas', views.ListaPrecioViewSet, basename='listas')
router.register(r'precios-articulo', views.PrecioArticuloViewSet, basename='precios-articulo')
router.register(r'reglas', views.ReglaPrecioViewSet, basename='reglas')
router.register(r'combinaciones', views.CombinacionProductoViewSet, basename='combinaciones')

# readonly lookup
router.register(r'empresas', views.EmpresaViewSet, basename='empresas')
router.register(r'sucursales', views.SucursalViewSet, basename='sucursales')
router.register(r'articulos', views.ArticuloViewSet, basename='articulos')

urlpatterns = [
    path('', views.index, name='listas_index'),
    path('api/precio/calcular/', views.CalcularPrecioAPIView.as_view(), name='api_calcular_precio'),
    path('api/', include(router.urls)),
    path('dashboard/', views.dashboard, name='dashboard'),

    # CRUD web
    path('listas/', views.ListaPrecioListView.as_view(), name='lista_list'),
    path('listas/<int:pk>/', views.ListaPrecioDetailView.as_view(), name='lista_detail'),
    path('listas/crear/', views.ListaPrecioCreateView.as_view(), name='lista_create'),
    path('listas/<int:pk>/editar/', views.ListaPrecioUpdateView.as_view(), name='lista_update'),
    path('listas/<int:pk>/eliminar/', views.ListaPrecioDeleteView.as_view(), name='lista_delete'),
    
    # rutas para reglas (agregar en listas/urls.py)
    path('reglas/', views.ReglaPrecioListView.as_view(), name='regla_list'),
    path('reglas/nueva/', views.ReglaPrecioCreateView.as_view(), name='regla_create'),
    path('reglas/<int:pk>/', views.ReglaPrecioDetailView.as_view(), name='regla_detail'),
    path('reglas/<int:pk>/editar/', views.ReglaPrecioUpdateView.as_view(), name='regla_update'),
    path('reglas/<int:pk>/borrar/', views.ReglaPrecioDeleteView.as_view(), name='regla_delete'),
    
    # precios por artículo (web)
    path('precios/', views.PrecioArticuloListView.as_view(), name='precio_list'),
    path('precios/nuevo/', views.PrecioArticuloCreateView.as_view(), name='precio_create'),
    path('precios/<int:pk>/', views.PrecioArticuloDetailView.as_view(), name='precio_detail'),
    path('precios/<int:pk>/update/', views.PrecioArticuloUpdateView.as_view(), name='precio_update'),
    path('precios/<int:pk>/borrar/', views.PrecioArticuloDeleteView.as_view(), name='precio_delete'),

    # rutas para artículos
    path('articulos/', views.ArticuloListView.as_view(), name='articulo_list'),
    path('articulos/<int:pk>/', views.ArticuloDetailView.as_view(), name='articulo_detail'),
    path('articulos/nuevo/', views.ArticuloCreateView.as_view(), name='articulo_create'),
    path('articulos/<int:pk>/editar/', views.ArticuloUpdateView.as_view(), name='articulo_update'),
    path('articulos/<int:pk>/borrar/', views.ArticuloDeleteView.as_view(), name='articulo_delete'),
    
    # listas/urls.py
    path('lineas/', views.LineaArticuloListView.as_view(), name='linea_list'),
    path('lineas/<int:pk>/', views.LineaArticuloDetailView.as_view(), name='linea_detail'),
    path('lineas/nuevo/', views.LineaArticuloCreateView.as_view(), name='linea_create'),
    path('lineas/<int:pk>/editar/', views.LineaArticuloUpdateView.as_view(), name='linea_update'),
    path('lineas/<int:pk>/borrar/', views.LineaArticuloDeleteView.as_view(), name='linea_delete'),

    path('grupos/', views.GrupoArticuloListView.as_view(), name='grupo_list'),
    path('grupos/<int:pk>/', views.GrupoArticuloDetailView.as_view(), name='grupo_detail'),
    path('grupos/nuevo/', views.GrupoArticuloCreateView.as_view(), name='grupo_create'),
    path('grupos/<int:pk>/editar/', views.GrupoArticuloUpdateView.as_view(), name='grupo_update'),
    path('grupos/<int:pk>/borrar/', views.GrupoArticuloDeleteView.as_view(), name='grupo_delete'),
    
    path('ordenes/', views.OrdenListView.as_view(), name='orden_list'),
    path('orden/<int:pk>/', views.OrdenDetailView.as_view(), name='orden_detail'),
    path('orden/nueva/', views.orden_create_view, name='orden_create'),
    path('orden/<int:pk>/editar/', views.orden_update_view, name='orden_update'),
    path('orden/<int:pk>/eliminar/', views.OrdenDeleteView.as_view(), name='orden_delete'),
    path('orden/<int:orden_id>/confirmar/', views.confirmar_orden, name='confirmar_orden'),
    
    path('combinaciones/', views.CombinacionListView.as_view(), name='combinacion_list'),
    path('combinaciones/nueva/', views.CombinacionCreateView.as_view(), name='combinacion_create'),
    path('combinaciones/<int:pk>/', views.CombinacionDetailView.as_view(), name='combinacion_detail'),
    path('combinaciones/<int:pk>/editar/', views.CombinacionUpdateView.as_view(), name='combinacion_update'),
    path('combinaciones/<int:pk>/eliminar/', views.CombinacionDeleteView.as_view(), name='combinacion_delete'),

]
