from rest_framework import serializers
from apps.inventory.models import StorageRoom
from .models import TemperatureLog, TemperatureAlert


class TemperatureLogSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.room_name', read_only=True)
    cold_storage_name = serializers.CharField(source='room.cold_storage.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.name', read_only=True, allow_null=True)

    class Meta:
        model = TemperatureLog
        fields = [
            'id', 'room', 'room_name', 'cold_storage_name', 'logged_at', 'temperature',
            'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['created_by']


class TemperatureAlertSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.room_name', read_only=True)
    cold_storage_name = serializers.CharField(source='room.cold_storage.name', read_only=True)
    room_min_temp = serializers.DecimalField(source='room.min_temperature', read_only=True, max_digits=5, decimal_places=2)
    room_max_temp = serializers.DecimalField(source='room.max_temperature', read_only=True, max_digits=5, decimal_places=2)
    acknowledged_by_name = serializers.CharField(source='acknowledged_by.name', read_only=True, allow_null=True)
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = TemperatureAlert
        fields = [
            'id', 'room', 'room_name', 'cold_storage_name', 'room_min_temp', 'room_max_temp',
            'temperature', 'severity', 'status', 'message',
            'acknowledged_by', 'acknowledged_by_name', 'acknowledged_at',
            'resolved_at', 'action_taken', 'time_ago', 'created_at'
        ]

    def get_time_ago(self, obj):
        from django.utils import timezone
        delta = timezone.now() - obj.created_at
        minutes = int(delta.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes} mins ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours} hours ago"
        days = hours // 24
        return f"{days} days ago"


class TakeAlertActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['acknowledge', 'resolve'])
    action_taken = serializers.CharField(required=False, allow_blank=True)
