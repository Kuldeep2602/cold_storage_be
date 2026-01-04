from rest_framework import serializers
from .models import StorageRoom, TemperatureLog, TemperatureAlert


class StorageRoomSerializer(serializers.ModelSerializer):
    is_within_range = serializers.ReadOnlyField()
    temperature_status = serializers.ReadOnlyField()
    
    class Meta:
        model = StorageRoom
        fields = [
            'id', 'name', 'min_temperature', 'max_temperature', 
            'current_temperature', 'is_active', 'is_within_range',
            'temperature_status', 'created_at', 'updated_at'
        ]


class TemperatureLogSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)

    class Meta:
        model = TemperatureLog
        fields = [
            'id', 'room', 'room_name', 'logged_at', 'temperature',
            'created_by', 'created_by_name', 'created_at'
        ]
        read_only_fields = ['created_by']


class TemperatureAlertSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)
    room_min_temp = serializers.DecimalField(source='room.min_temperature', read_only=True, max_digits=5, decimal_places=2)
    room_max_temp = serializers.DecimalField(source='room.max_temperature', read_only=True, max_digits=5, decimal_places=2)
    acknowledged_by_name = serializers.CharField(source='acknowledged_by.name', read_only=True)
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = TemperatureAlert
        fields = [
            'id', 'room', 'room_name', 'room_min_temp', 'room_max_temp',
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
