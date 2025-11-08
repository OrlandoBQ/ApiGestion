# listas/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.views import APIView
from django.http import JsonResponse
from django.db import transaction
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from .forms import ListaPrecioForm, ReglaPrecioForm, PrecioArticuloForm, ArticuloForm, LineaArticuloForm, GrupoArticuloForm, OrdenForm, LineaOrdenFormSet, CombinacionProductoForm
from .models import ListaPrecio, PrecioArticulo, ReglaPrecio, CombinacionProducto, Empresa, Sucursal, Articulo , LineaArticulo, GrupoArticulo, Orden, LineaOrden   
from .serializers import LineaArticuloSerializer, GrupoArticuloSerializer, ListaPrecioSerializer, PrecioArticuloSerializer, ReglaPrecioSerializer, CombinacionProductoSerializer, EmpresaSerializer, SucursalSerializer, ArticuloSerializer, PrecioConsultaSerializer, PrecioResultadoSerializer
from .services import PrecioService
from django.contrib.auth.decorators import login_required

# ---------- Vista web base ----------
def index(request):
    return render(request, 'listas/index.html')

def login_view(request):
    if request.user.is_authenticated:
        # Ya está logueado, igual usa la misma plantilla
        return render(request, 'registration/login.html')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Credenciales inválidas. Intenta nuevamente.')

    return render(request, 'registration/login.html')


def logout_view(request):
    logout(request)
    return redirect('landing')

# ---------- Vista de Dashboard ----------
@login_required
def dashboard(request):
    listas = ListaPrecio.objects.select_related('empresa').order_by('-fecha_inicio')[:5]
    return render(request, 'dashboard.html', {'listas': listas})

@login_required
def dashboard(request):
    # métricas
    total_listas = ListaPrecio.objects.count()
    listas_vigentes = ListaPrecio.objects.filter(estado='vigente').count()
    total_reglas = ReglaPrecio.objects.filter(activo=True).count()
    total_combinaciones = CombinacionProducto.objects.count()
    total_precios_articulo = PrecioArticulo.objects.count()
    total_empresas = Empresa.objects.count()
    total_sucursales = Sucursal.objects.count()
    total_articulos = Articulo.objects.count()

    # últimas listas
    ultimas_listas = ListaPrecio.objects.select_related('empresa', 'sucursal') \
        .order_by('-fecha_inicio')[:5]

    # órdenes pendientes (ejemplo: estado 'borrador' como pendiente)
    from .models import Orden  # colócalo en imports al inicio si prefieres
    pending_orders = Orden.objects.filter(estado='borrador').count()

    context = {
        'user': request.user,
        'total_listas': total_listas,
        'listas_vigentes': listas_vigentes,
        'total_reglas': total_reglas,
        'total_combinaciones': total_combinaciones,
        'total_precios_articulo': total_precios_articulo,
        'total_empresas': total_empresas,
        'total_sucursales': total_sucursales,
        'total_articulos': total_articulos,
        'listas': ultimas_listas,
        'pending_orders': pending_orders,
    }
    return render(request, 'dashboard.html', context)


# ---------- API: cálculo de precio ----------
class CalcularPrecioAPIView(APIView):
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PrecioConsultaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        empresa = get_object_or_404(Empresa, pk=data['empresa_id'])
        sucursal = get_object_or_404(Sucursal, pk=data['sucursal_id'])
        articulo = get_object_or_404(Articulo, pk=data['articulo_id'])

        # aceptar carrito opcional: [{'articulo_id':..,'cantidad':..}, ...]
        carrito = request.data.get('carrito', None)

        res = PrecioService.calcular_precio(
            empresa=empresa,
            sucursal=sucursal,
            articulo=articulo,
            canal=data.get('canal') or None,
            cantidad=data.get('cantidad', 1),
            monto_pedido=data.get('monto_pedido'),
            fecha=data.get('fecha'),
            carrito_articulos=carrito
        )

        out_serializer = PrecioResultadoSerializer(data=res)
        if not out_serializer.is_valid():
            return Response(res, status=status.HTTP_200_OK)
        return Response(out_serializer.data, status=status.HTTP_200_OK)


# ---------- ViewSets CRUD ----------
class ListaPrecioViewSet(viewsets.ModelViewSet):
    queryset = ListaPrecio.objects.all().order_by('-fecha_inicio')
    serializer_class = ListaPrecioSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        empresa = self.request.query_params.get('empresa_id')
        sucursal = self.request.query_params.get('sucursal_id')
        if empresa:
            qs = qs.filter(empresa_id=empresa)
        if sucursal:
            qs = qs.filter(sucursal_id=sucursal)
        return qs


class PrecioArticuloViewSet(viewsets.ModelViewSet):
    queryset = PrecioArticulo.objects.select_related('lista', 'articulo').all()
    serializer_class = PrecioArticuloSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        lista = self.request.query_params.get('lista_id')
        articulo = self.request.query_params.get('articulo_id')
        if lista:
            qs = qs.filter(lista_id=lista)
        if articulo:
            qs = qs.filter(articulo_id=articulo)
        return qs


class ReglaPrecioViewSet(viewsets.ModelViewSet):
    queryset = ReglaPrecio.objects.select_related('lista').all().order_by('prioridad')
    serializer_class = ReglaPrecioSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        lista = self.request.query_params.get('lista_id')
        if lista:
            qs = qs.filter(lista_id=lista)
        return qs


class CombinacionProductoViewSet(viewsets.ModelViewSet):
    queryset = CombinacionProducto.objects.prefetch_related('articulos').all()
    serializer_class = CombinacionProductoSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        lista = self.request.query_params.get('lista_id')
        if lista:
            qs = qs.filter(lista_id=lista)
        return qs


# ---------- Readonly lookup ViewSets ----------
class EmpresaViewSet(viewsets.ModelViewSet):
    queryset = Empresa.objects.all()
    serializer_class = EmpresaSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

class SucursalViewSet(viewsets.ModelViewSet):
    queryset = Sucursal.objects.all()
    serializer_class = SucursalSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

class ArticuloViewSet(viewsets.ModelViewSet):
    queryset = Articulo.objects.all()
    serializer_class = ArticuloSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]


class LineaArticuloViewSet(viewsets.ModelViewSet):
    queryset = LineaArticulo.objects.all()
    serializer_class = LineaArticuloSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]


class GrupoArticuloViewSet(viewsets.ModelViewSet):
    queryset = GrupoArticulo.objects.all()
    serializer_class = GrupoArticuloSerializer
    authentication_classes = [TokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

# CRUD web para ListaPrecio (no-admin)
class ListaPrecioListView(LoginRequiredMixin, ListView):
    model = ListaPrecio
    template_name = 'listas/lista_list.html'
    context_object_name = 'listas'
    paginate_by = 12
    ordering = ['-fecha_inicio']


class ListaPrecioDetailView(LoginRequiredMixin, DetailView):
    model = ListaPrecio
    template_name = 'listas/lista_detail.html'
    context_object_name = 'lista'


class ListaPrecioCreateView(LoginRequiredMixin, CreateView):
    model = ListaPrecio
    form_class = ListaPrecioForm
    template_name = 'listas/lista_form.html'
    success_url = reverse_lazy('listas:lista_list')


class ListaPrecioUpdateView(LoginRequiredMixin, UpdateView):
    model = ListaPrecio
    form_class = ListaPrecioForm
    template_name = 'listas/lista_form.html'
    success_url = reverse_lazy('listas:lista_list')


class ListaPrecioDeleteView(LoginRequiredMixin, DeleteView):
    model = ListaPrecio
    template_name = 'listas/lista_confirm_delete.html'
    success_url = reverse_lazy('listas:lista_list')

# CRUD web para ReglaPrecio (añadir al final de listas/views.py)
class ReglaPrecioListView(LoginRequiredMixin, ListView):
    model = ReglaPrecio
    template_name = 'listas/regla_list.html'
    context_object_name = 'reglas'
    paginate_by = 20
    ordering = ['prioridad', '-id']


class ReglaPrecioDetailView(LoginRequiredMixin, DetailView):
    model = ReglaPrecio
    template_name = 'listas/regla_detail.html'
    context_object_name = 'regla'


class ReglaPrecioCreateView(LoginRequiredMixin, CreateView):
    model = ReglaPrecio
    form_class = ReglaPrecioForm
    template_name = 'listas/regla_form.html'
    success_url = reverse_lazy('listas:regla_list')


class ReglaPrecioUpdateView(LoginRequiredMixin, UpdateView):
    model = ReglaPrecio
    form_class = ReglaPrecioForm
    template_name = 'listas/regla_form.html'
    success_url = reverse_lazy('listas:regla_list')


class ReglaPrecioDeleteView(LoginRequiredMixin, DeleteView):
    model = ReglaPrecio
    template_name = 'listas/regla_confirm_delete.html'
    success_url = reverse_lazy('listas:regla_list')

# CRUD web para PrecioArticulo
class PrecioArticuloListView(LoginRequiredMixin, ListView):
    model = PrecioArticulo
    template_name = 'listas/precioarticulo_list.html'
    context_object_name = 'precios'
    paginate_by = 20
    ordering = ['-id']


class PrecioArticuloDetailView(LoginRequiredMixin, DetailView):
    model = PrecioArticulo
    template_name = 'listas/precioarticulo_detail.html'
    context_object_name = 'precio'


class PrecioArticuloCreateView(LoginRequiredMixin, CreateView):
    model = PrecioArticulo
    form_class = PrecioArticuloForm
    template_name = 'listas/precioarticulo_form.html'
    success_url = reverse_lazy('listas:precio_list')


class PrecioArticuloUpdateView(LoginRequiredMixin, UpdateView):
    model = PrecioArticulo
    form_class = PrecioArticuloForm
    template_name = 'listas/precioarticulo_form.html'
    success_url = reverse_lazy('listas:precio_list')


class PrecioArticuloDeleteView(LoginRequiredMixin, DeleteView):
    model = PrecioArticulo
    template_name = 'listas/precioarticulo_confirm_delete.html'
    success_url = reverse_lazy('listas:precio_list')


# Lista de artículos
class ArticuloListView(ListView):
    model = Articulo
    template_name = "listas/articulo_list.html"
    context_object_name = "articulos"

# Detalle de un artículo
class ArticuloDetailView(DetailView):
    model = Articulo
    template_name = "listas/articulo_detail.html"
    context_object_name = "articulo"

# Crear un artículo
class ArticuloCreateView(CreateView):
    model = Articulo
    form_class = ArticuloForm
    template_name = "listas/articulo_form.html"
    success_url = reverse_lazy("listas:articulo_list")

# Editar un artículo
class ArticuloUpdateView(UpdateView):
    model = Articulo
    form_class = ArticuloForm
    template_name = "listas/articulo_form.html"
    success_url = reverse_lazy("listas:articulo_list")
 
# Borrar un artículo   
class ArticuloDeleteView(DeleteView):
    model = Articulo
    template_name = "listas/articulo_confirm_delete.html"
    success_url = reverse_lazy("listas:articulo_list")
    

# --- LíneaArticulo ---
class LineaArticuloListView(LoginRequiredMixin, ListView):
    model = LineaArticulo
    template_name = 'listas/linea_list.html'
    context_object_name = 'lineas'
    paginate_by = 20
    ordering = ['nombre']


class LineaArticuloDetailView(LoginRequiredMixin, DetailView):
    model = LineaArticulo
    template_name = 'listas/linea_detail.html'
    context_object_name = 'linea'


class LineaArticuloCreateView(LoginRequiredMixin, CreateView):
    model = LineaArticulo
    form_class = LineaArticuloForm
    template_name = 'listas/linea_form.html'
    success_url = reverse_lazy('listas:linea_list')


class LineaArticuloUpdateView(LoginRequiredMixin, UpdateView):
    model = LineaArticulo
    form_class = LineaArticuloForm
    template_name = 'listas/linea_form.html'
    success_url = reverse_lazy('listas:linea_list')


class LineaArticuloDeleteView(LoginRequiredMixin, DeleteView):
    model = LineaArticulo
    template_name = 'listas/linea_confirm_delete.html'
    success_url = reverse_lazy('listas:linea_list')


# ------------------------------
# CRUD web para Grupo de Artículo
# ------------------------------

class GrupoArticuloListView(LoginRequiredMixin, ListView):
    model = GrupoArticulo
    template_name = 'listas/grupo_list.html'
    context_object_name = 'grupos'
    paginate_by = 20
    ordering = ['linea__nombre', 'nombre']


class GrupoArticuloDetailView(LoginRequiredMixin, DetailView):
    model = GrupoArticulo
    template_name = 'listas/grupo_detail.html'
    context_object_name = 'grupo'


class GrupoArticuloCreateView(LoginRequiredMixin, CreateView):
    model = GrupoArticulo
    form_class = GrupoArticuloForm
    template_name = 'listas/grupo_form.html'
    success_url = reverse_lazy('listas:grupo_list')


class GrupoArticuloUpdateView(LoginRequiredMixin, UpdateView):
    model = GrupoArticulo
    form_class = GrupoArticuloForm
    template_name = 'listas/grupo_form.html'
    success_url = reverse_lazy('listas:grupo_list')


class GrupoArticuloDeleteView(LoginRequiredMixin, DeleteView):
    model = GrupoArticulo
    template_name = 'listas/grupo_confirm_delete.html'
    success_url = reverse_lazy('listas:grupo_list')


# Lista de órdenes
class OrdenListView(ListView):
    model = Orden
    template_name = 'listas/orden_list.html'
    context_object_name = 'object_list'
    paginate_by = 20
    ordering = ['-fecha']

# Detalle (ya tienes template)
class OrdenDetailView(DetailView):
    model = Orden
    template_name = 'listas/orden_detail.html'
    context_object_name = 'orden'

# Crear orden con inline formset
def orden_create_view(request):
    if request.method == 'POST':
        form = OrdenForm(request.POST)
        formset = LineaOrdenFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            orden = form.save(commit=False)
            orden.save()
            formset.instance = orden
            formset.save()
            messages.success(request, 'Orden creada correctamente.')
            return redirect('listas:orden_detail', pk=orden.pk)
    else:
        form = OrdenForm()
        formset = LineaOrdenFormSet()
    return render(request, 'listas/orden_form.html', {'form': form, 'formset': formset})

# Editar orden con inline formset
def orden_update_view(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    if request.method == 'POST':
        form = OrdenForm(request.POST, instance=orden)
        formset = LineaOrdenFormSet(request.POST, instance=orden)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Orden actualizada correctamente.')
            return redirect('listas:orden_detail', pk=orden.pk)
    else:
        form = OrdenForm(instance=orden)
        formset = LineaOrdenFormSet(instance=orden)
    return render(request, 'listas/orden_form.html', {'form': form, 'formset': formset, 'orden': orden})

# Eliminar orden
class OrdenDeleteView(DeleteView):
    model = Orden
    template_name = 'listas/orden_confirm_delete.html'
    success_url = reverse_lazy('listas:orden_list')

# Confirmar orden (acción POST)
def confirmar_orden(request, orden_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    orden = get_object_or_404(Orden, pk=orden_id)
    empresa = orden.empresa
    sucursal = orden.sucursal
    canal = getattr(orden, 'canal', None)
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
            # si viene de browser, mostrar mensajes y redirigir; si es API, devolver JSON
            if request.is_ajax() or request.content_type == 'application/json':
                return JsonResponse({'ok': False, 'errors': errores}, status=400)
            messages.error(request, "No se pudo confirmar la orden: " + "; ".join(errores))
            return redirect('listas:orden_detail', pk=orden.pk)
        orden.estado = 'confirmada'
        orden.save()
    if request.is_ajax() or request.content_type == 'application/json':
        return JsonResponse({'ok': True})
    messages.success(request, 'Orden confirmada correctamente.')
    return redirect('listas:orden_detail', pk=orden.pk)

# CRUD web para CombinacionProducto
class CombinacionListView(LoginRequiredMixin, ListView):
    model = CombinacionProducto
    template_name = 'listas/combinacion_list.html'
    context_object_name = 'combinaciones'
    paginate_by = 20
    ordering = ['-id']

    def get_queryset(self):
        qs = super().get_queryset().select_related('lista').prefetch_related('articulos')
        lista_id = self.request.GET.get('lista_id')
        if lista_id:
            qs = qs.filter(lista_id=lista_id)
        return qs

class CombinacionDetailView(LoginRequiredMixin, DetailView):
    model = CombinacionProducto
    template_name = 'listas/combinacion_detail.html'
    context_object_name = 'combinacion'

class CombinacionCreateView(LoginRequiredMixin, CreateView):
    model = CombinacionProducto
    form_class = CombinacionProductoForm
    template_name = 'listas/combinacion_form.html'
    success_url = reverse_lazy('listas:combinacion_list')

    def form_valid(self, form):
        resp = super().form_valid(form)
        # asegúrate de setear M2M (CreateView hace save y form.save_m2m al final)
        return resp

class CombinacionUpdateView(LoginRequiredMixin, UpdateView):
    model = CombinacionProducto
    form_class = CombinacionProductoForm
    template_name = 'listas/combinacion_form.html'
    success_url = reverse_lazy('listas:combinacion_list')

class CombinacionDeleteView(LoginRequiredMixin, DeleteView):
    model = CombinacionProducto
    template_name = 'listas/combinacion_confirm_delete.html'
    success_url = reverse_lazy('listas:combinacion_list')