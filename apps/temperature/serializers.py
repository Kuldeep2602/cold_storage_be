from rest_framework import serializers

from .models import TemperatureLog


class TemperatureLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemperatureLog
        fields = ['id', 'logged_at', 'temperature', 'created_by', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']
