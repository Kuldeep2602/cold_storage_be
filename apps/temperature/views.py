from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count, Q
from django.utils import timezone

from apps.inventory.models import StorageRoom
from .models import TemperatureLog, TemperatureAlert, AlertStatus
from .serializers import (
    TemperatureLogSerializer, 
    TemperatureAlertSerializer,
    TakeAlertActionSerializer
)


class TemperatureLogViewSet(viewsets.ModelViewSet):
    queryset = TemperatureLog.objects.select_related('room', 'room__cold_storage', 'created_by').all()
    serializer_class = TemperatureLogSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        
        # Filter by user's assigned storages
        if user.role in ['technician', 'operator', 'manager']:
            assigned_storage_ids = user.assigned_storages.values_list('id', flat=True)
            queryset = queryset.filter(room__cold_storage_id__in=assigned_storage_ids)
        elif user.role == 'owner':
            queryset = queryset.filter(room__cold_storage__owner=user)
        
        room_id = self.request.query_params.get('room')
        if room_id:
            queryset = queryset.filter(room_id=room_id)
        return queryset
    
    @action(detail=False, methods=['post'], url_path='log-temperature')
    def log_temperature(self, request):
        """Log temperature for a room (for technicians)"""
        room_id = request.data.get('room_id')
        temperature = request.data.get('temperature')
        
        if not room_id or temperature is None:
            return Response(
                {'detail': 'room_id and temperature are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            temperature = float(temperature)
        except (ValueError, TypeError):
            return Response(
                {'detail': 'Invalid temperature value'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get room and verify access
        try:
            room = StorageRoom.objects.select_related('cold_storage', 'cold_storage__owner').get(id=room_id)
            
            # Verify user has access to this room's cold storage
            user = request.user
            if user.role in ['technician', 'operator', 'manager']:
                if not user.assigned_storages.filter(id=room.cold_storage_id).exists():
                    return Response(
                        {'detail': 'You do not have access to this storage room'}, 
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif user.role == 'owner':
                if room.cold_storage.owner != user:
                    return Response(
                        {'detail': 'You do not have access to this storage room'}, 
                        status=status.HTTP_403_FORBIDDEN
                    )
        except StorageRoom.DoesNotExist:
            return Response(
                {'detail': 'Storage room not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Update room's current temperature
        room.current_temperature = temperature
        room.last_temp_update = timezone.now()
        room.save()
        
        # Create temperature log
        temp_log = TemperatureLog.objects.create(
            room=room,
            logged_at=timezone.now(),
            temperature=temperature,
            created_by=request.user
        )
        
        # Check if temperature is out of range and create alert
        alert_created = False
        if not room.is_within_range:
            # Check if there's already an active alert for this room
            existing_active = TemperatureAlert.objects.filter(
                room=room, 
                status=AlertStatus.ACTIVE
            ).exists()
            
            if not existing_active:
                temp_status = room.temperature_status
                severity_map = {
                    'warning': 'medium',
                    'critical': 'high'
                }
                severity = severity_map.get(temp_status, 'medium')
                
                TemperatureAlert.objects.create(
                    room=room,
                    temperature=temperature,
                    severity=severity,
                    message=f"Temperature {temperature}°C is outside the allowed range ({room.min_temperature}°C to {room.max_temperature}°C)"
                )
                alert_created = True
        
        return Response({
            'success': True,
            'temperature': temperature,
            'room_name': room.room_name,
            'status': room.temperature_status,
            'is_within_range': room.is_within_range,
            'alert_created': alert_created,
            'log_id': temp_log.id
        })


class TemperatureAlertViewSet(viewsets.ModelViewSet):
    queryset = TemperatureAlert.objects.select_related('room', 'room__cold_storage', 'acknowledged_by').all()
    serializer_class = TemperatureAlertSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch']

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()

        # Filter by user's assigned storages
        if user.role in ['technician', 'operator', 'manager']:
            assigned_storage_ids = user.assigned_storages.values_list('id', flat=True)
            queryset = queryset.filter(room__cold_storage_id__in=assigned_storage_ids)
        elif user.role == 'owner':
            queryset = queryset.filter(room__cold_storage__owner=user)

        # Apply cold_storage query parameter filter if provided
        cold_storage_id = self.request.query_params.get('cold_storage')
        if cold_storage_id:
            queryset = queryset.filter(room__cold_storage_id=cold_storage_id)

        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        severity_filter = self.request.query_params.get('severity')
        if severity_filter:
            queryset = queryset.filter(severity=severity_filter)

        return queryset

    @action(detail=False, methods=['get'], url_path='active-count')
    def active_count(self, request):
        """Get count of active alerts for user's storages"""
        count = self.get_queryset().filter(status=AlertStatus.ACTIVE).count()
        return Response({'count': count})

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """Get alert summary by status and severity"""
        queryset = self.get_queryset()
        status_counts = queryset.values('status').annotate(count=Count('id'))
        severity_counts = queryset.filter(
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
