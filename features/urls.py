# notelib_server/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("features/import/", views.import_feature, name="import_feature"),
    path("features/list/", views.list_features, name="list_features"),
    path("features/exec/", views.exec, name="exec_feature"),
    path("features/load_notebook/", views.load_notebook, name="load_notebook"),
    path("features/registry/", views.registry, name="registry"),
]
