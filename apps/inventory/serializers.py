from rest_framework import serializers

from .models import InwardEntry, OutwardEntry, Person


class PersonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Person
        fields = ['id', 'person_type', 'name', 'mobile_number', 'address', 'created_at']
        read_only_fields = ['id', 'created_at']


class InwardEntrySerializer(serializers.ModelSerializer):
	remaining_quantity = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True)

	class Meta:
		model = InwardEntry
		fields = [
			'id',
			'person',
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
