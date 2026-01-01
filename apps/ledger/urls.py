from django.urls import path

from .views import LedgerView

urlpatterns = [
    path('', LedgerView.as_view(), name='ledger'),
]
