from rest_framework import serializers

from .models import PaymentRequest


class PaymentRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentRequest
        fields = ['id', 'outward_entry', 'status', 'method', 'payload', 'created_at']
        read_only_fields = ['id', 'created_at']
