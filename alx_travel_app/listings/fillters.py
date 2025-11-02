from django_filters import rest_framework as filters


from .models import Listing

class ListingFilter(filters.FilterSet):
    min_price = filters.NumberFilter(field_name="price_per_night", lookup_expr='gte')
    max_price = filters.NumberFilter(field_name="price_per_night", lookup_expr='lte')

    class Meta:
        model = Listing
        fields = ['location', 'price_per_night']