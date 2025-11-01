from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render
from listas import views as listas_views  # importar vistas personalizadas

def landing(request):
    features = [
        "Control Centralizado",
        "Reglas Automáticas",
        "Auditoría y Trazabilidad",
        "Integración Sencilla",
    ]
    return render(request, 'landing.html', {'features': features})

urlpatterns = [
    path('', landing, name='landing'),
    path('login/', listas_views.login_view, name='login'),  # tu vista de login personalizada
    path('logout/', listas_views.logout_view, name='logout'),  # para cerrar sesión
    path('admin/', admin.site.urls),
    path('listas/', include('listas.urls')),
]
