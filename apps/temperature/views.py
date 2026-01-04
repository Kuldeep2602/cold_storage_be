from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count, Q

from .models import StorageRoom, TemperatureLog, TemperatureAlert, AlertStatus
from .serializers import (
    StorageRoomSerializer, 
    TemperatureLogSerializer, 
    TemperatureAlertSerializer,
    TakeAlertActionSerializer
)


class StorageRoomViewSet(viewsets.ModelViewSet):
    queryset = StorageRoom.objects.all().order_by('name')
    serializer_class = StorageRoomSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'], url_path='update-temperature')
    def update_temperature(self, request, pk=None):
        """Update current temperature for a room and create alert if out of range"""
        room = self.get_object()
        temperature = request.data.get('temperature')
        
        if temperature is None:
            return Response({'detail': 'Temperature is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            temperature = float(temperature)
        except (ValueError, TypeError):
            return Response({'detail': 'Invalid temperature value'}, status=status.HTTP_400_BAD_REQUEST)
        
        room.current_temperature = temperature
        room.save()
        
        # Create temperature log
        from django.utils import timezone
        TemperatureLog.objects.create(
            room=room,
            logged_at=timezone.now(),
            temperature=temperature,
            created_by=request.user
        )
        
        # Check if temperature is out of range and create alert
        if not room.is_within_range:
            # Check if there's already an active alert for this room
            existing_active = TemperatureAlert.objects.filter(
                room=room, 
                status=AlertStatus.ACTIVE
            ).exists()
            
            if not existing_active:
                severity = room.temperature_status
                TemperatureAlert.objects.create(
                    room=room,
                    temperature=temperature,
                    severity=severity,
                    message=f"Temperature {temperature}°C is outside the allowed range ({room.min_temperature}°C to {room.max_temperature}°C)"
                )
        
        return Response(StorageRoomSerializer(room).data)


class TemperatureLogViewSet(viewsets.ModelViewSet):
    queryset = TemperatureLog.objects.all()
    serializer_class = TemperatureLogSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        queryset = super().get_queryset()
        room_id = self.request.query_params.get('room')
        if room_id:
            queryset = queryset.filter(room_id=room_id)
        return queryset


class TemperatureAlertViewSet(viewsets.ModelViewSet):
    queryset = TemperatureAlert.objects.all()
    serializer_class = TemperatureAlertSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        severity_filter = self.request.query_params.get('severity')
        if severity_filter:
            queryset = queryset.filter(severity=severity_filter)
            
        return queryset

    @action(detail=False, methods=['get'], url_path='active-count')
    def active_count(self, request):
        """Get count of active alerts"""
        count = TemperatureAlert.objects.filter(status=AlertStatus.ACTIVE).count()
        return Response({'count': count})

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """Get alert summary by status and severity"""
        status_counts = TemperatureAlert.objects.values('status').annotate(count=Count('id'))
        severity_counts = TemperatureAlert.objects.filter(
            status=AlertStatus.ACTIVE
        ).values('severity').annotate(count=Count('id'))
        
        return Response({
            'by_status': {item['status']: item['count'] for item in status_counts},
            'active_by_severity': {item['severity']: item['count'] for item in severity_counts}
        })

    @action(detail=True, methods=['post'], url_path='take-action')
    def take_action(self, request, pk=None):
        """Acknowledge or resolve an alert"""
        alert = self.get_object()
        serializer = TakeAlertActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        action_type = serializer.validated_data['action']
        action_taken = serializer.validated_data.get('action_taken', '')
        
        if action_type == 'acknowledge':
            alert.acknowledge(request.user)
        elif action_type == 'resolve':
            alert.resolve(action_taken)
        
        return Response(TemperatureAlertSerializer(alert).data)
