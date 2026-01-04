from rest_framework import serializers
from django.db.models import Sum

from .models import ColdStorage, InwardEntry, OutwardEntry, Person


class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'person_type', 'name', 'mobile_number', 'address', 'created_at']
        read_only_fields = ['id', 'created_at']


class ColdStorageSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.name', read_only=True)
    manager_name = serializers.CharField(source='manager.name', read_only=True, allow_null=True)
    display_name = serializers.CharField(read_only=True)
    occupied_capacity = serializers.SerializerMethodField()
    available_capacity = serializers.SerializerMethodField()
    utilization_percent = serializers.SerializerMethodField()

    class Meta:
        model = ColdStorage
        fields = [
            'id', 'name', 'code', 'display_name', 'address', 'city', 'state',
            'total_capacity', 'occupied_capacity', 'available_capacity', 'utilization_percent',
            'owner', 'owner_name', 'manager', 'manager_name',
            'contact_phone', 'contact_email', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_occupied_capacity(self, obj):
        """Calculate occupied capacity from inventory"""
        total_inward = InwardEntry.objects.filter(cold_storage=obj).aggregate(
            total=Sum('quantity')
        )['total'] or 0
        
        total_outward = 0
        for inward in InwardEntry.objects.filter(cold_storage=obj):
            total_outward += inward.outward_total_quantity
        
        return float(total_inward) - float(total_outward)

    def get_available_capacity(self, obj):
        occupied = self.get_occupied_capacity(obj)
        return max(0, float(obj.total_capacity) - occupied)

    def get_utilization_percent(self, obj):
        if obj.total_capacity == 0:
            return 0
        occupied = self.get_occupied_capacity(obj)
        return round((occupied / float(obj.total_capacity)) * 100, 1)


class ColdStorageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ColdStorage
        fields = ['name', 'code', 'address', 'city', 'state', 'total_capacity', 
                  'manager', 'contact_phone', 'contact_email']

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class ColdStorageSummarySerializer(serializers.ModelSerializer):
    """Lightweight serializer for dropdown lists"""
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = ColdStorage
        fields = ['id', 'name', 'code', 'display_name', 'city']


class InwardEntrySerializer(serializers.ModelSerializer):
	remaining_quantity = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)
	cold_storage_name = serializers.CharField(source='cold_storage.name', read_only=True, allow_null=True)

	class Meta:
		model = InwardEntry
		fields = [
			'id',
			'person',
			'cold_storage',
			'cold_storage_name',
			'crop_name',
			'crop_variety',
			'size_grade',
			'quantity',
			'packaging_type',
			'quality_grade',
			'image',
			'rack_number',
			'storage_room',
			'expected_storage_duration_days',
			'entry_date',
			'created_by',
			'created_at',
			'remaining_quantity',
		]
		read_only_fields = ['id', 'created_by', 'created_at', 'entry_date', 'remaining_quantity']


class OutwardEntrySerializer(serializers.ModelSerializer):
    receipt_number = serializers.CharField(read_only=True)

    class Meta:
        model = OutwardEntry
        fields = [
            'id',
            'inward_entry',
            'quantity',
            'packaging_type',
            'receipt_number',
            'payment_status',
            'payment_method',
            'created_by',
            'created_at',
        ]
        read_only_fields = ['id', 'receipt_number', 'created_by', 'created_at']


class StockSerializer(serializers.Serializer):
    inward_entry_id = serializers.IntegerField()
    person_id = serializers.IntegerField()
    person_name = serializers.CharField()
    crop_name = serializers.CharField()
    crop_variety = serializers.CharField(allow_blank=True)
    packaging_type = serializers.CharField()
    total_quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    remaining_quantity = serializers.DecimalField(max_digits=12, decimal_places=3)


class OwnerDashboardStatsSerializer(serializers.Serializer):
    """Stats for a single cold storage in owner dashboard"""
    cold_storage_id = serializers.IntegerField()
    cold_storage_name = serializers.CharField()
    cold_storage_code = serializers.CharField()
    
    # Storage utilization
    total_capacity = serializers.DecimalField(max_digits=12, decimal_places=2)
    occupied_capacity = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_capacity = serializers.DecimalField(max_digits=12, decimal_places=2)
    utilization_percent = serializers.DecimalField(max_digits=5, decimal_places=1)
    
    # This month stats
    month_inflow = serializers.DecimalField(max_digits=12, decimal_places=2)
    month_outflow = serializers.DecimalField(max_digits=12, decimal_places=2)
    
    # Bookings
    active_bookings = serializers.IntegerField()
    confirmed_bookings = serializers.IntegerField()
    pending_bookings = serializers.IntegerField()
    
    # Alerts
    active_alerts = serializers.IntegerField()
    temperature_alerts = serializers.IntegerField()
    
    # Revenue (estimated)
    estimated_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    avg_storage_duration = serializers.IntegerField()
