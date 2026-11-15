from django.contrib import admin
from django.urls import include, path
from todos import views as todos_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('todos.urls')),
    path('accounts/', include('accounts.urls')),
    path('', todos_views.index, name='index'),
]
