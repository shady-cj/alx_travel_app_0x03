"""
Views for the listings app.
"""
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, AllowAny
from rest_framework.views import APIView
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView
from django.shortcuts import get_object_or_404
from django.db import models
from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend

from .fillters import ListingFilter

from .models import Listing, Booking, Review, User, BookingStatus, Payment, PaymentMethod
from .serializers import (
    ListingSerializer, 
    ListingCreateUpdateSerializer,
    BookingSerializer, 
    BookingCreateSerializer,
    ReviewSerializer,
    UserSerializer,
    UserCreateSerializer,
    PaymentSerializer
)
from .permissions import IsOwnerOrReadOnly, IsHostOrReadOnly
from .services import ChapaService
from .tasks import send_payment_confirmation_email, send_payment_failed_email
import logging
import uuid


logger = logging.getLogger(__name__)


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for User model.
    Provides CRUD operations for users.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = 'user_id'

    def get_serializer_class(self):
        """Use different serializers for different actions"""
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        """
        Allow anyone to register (create), but require authentication for other actions
        """
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Get current user's profile
        Endpoint: GET /api/users/me/
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def listings(self, request, user_id=None):
        """
        Get all listings for a specific user
        Endpoint: GET /api/users/{user_id}/listings/
        """
        user = self.get_object()
        listings = Listing.objects.filter(host=user)
        serializer = ListingSerializer(listings, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def bookings(self, request, user_id=None):
        """
        Get all bookings for a specific user
        Endpoint: GET /api/users/{user_id}/bookings/
        """
        user = self.get_object()
        bookings = Booking.objects.filter(user=user)
        serializer = BookingSerializer(bookings, many=True)
        return Response(serializer.data)


class ListingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Listing model.
    Provides full CRUD operations for property listings.
    
    List: GET /api/listings/
    Create: POST /api/listings/
    Retrieve: GET /api/listings/{property_id}/
    Update: PUT /api/listings/{property_id}/
    Partial Update: PATCH /api/listings/{property_id}/
    Delete: DELETE /api/listings/{property_id}/
    """
    queryset = Listing.objects.select_related('host').prefetch_related('reviews')
    serializer_class = ListingSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsHostOrReadOnly]
    lookup_field = 'property_id'
    
    # Add filtering, searching, and ordering
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ListingFilter
    search_fields = ['name', 'description', 'location']
    ordering_fields = ['price_per_night', 'created_at', 'name']
    ordering = ['-created_at']  # Default ordering

    def get_serializer_class(self):
        """
        Use different serializers for different actions
        """
        if self.action in ['create', 'update', 'partial_update']:
            return ListingCreateUpdateSerializer
        return ListingSerializer

    def perform_create(self, serializer):
        """
        Set the host to the current user when creating a listing
        """
        serializer.save(host=self.request.user)



    @action(detail=True, methods=['get'])
    def reviews(self, request, property_id=None):
        """
        Get all reviews for a specific listing
        Endpoint: GET /api/listings/{property_id}/reviews/
        """
        listing = self.get_object()
        reviews = listing.reviews.all()
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_review(self, request, property_id=None):
        """
        Add a review to a listing
        Endpoint: POST /api/listings/{property_id}/add_review/
        Body: {"rating": 5, "comment": "Great place!"}
        """
        listing = self.get_object()
        
        # Check if user has already reviewed this property
        if Review.objects.filter(listing=listing, user=request.user).exists():
            return Response(
                {'error': 'You have already reviewed this property'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = ReviewSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(listing=listing, user=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def bookings(self, request, property_id=None):
        """
        Get all bookings for a specific listing (host only)
        Endpoint: GET /api/listings/{property_id}/bookings/
        """
        listing = self.get_object()
        
        # Only allow host to see all bookings
        if request.user != listing.host:
            return Response(
                {'error': 'Only the host can view all bookings for this property'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        bookings = listing.bookings.all()
        serializer = BookingSerializer(bookings, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_listings(self, request):
        """
        Get all listings for the current user
        Endpoint: GET /api/listings/my_listings/
        """
        listings = Listing.objects.filter(host=request.user)
        serializer = self.get_serializer(listings, many=True)
        return Response(serializer.data)


class BookingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Booking model.
    Provides full CRUD operations for bookings.
    
    List: GET /api/bookings/
    Create: POST /api/bookings/
    Retrieve: GET /api/bookings/{booking_id}/
    Update: PUT /api/bookings/{booking_id}/
    Partial Update: PATCH /api/bookings/{booking_id}/
    Delete: DELETE /api/bookings/{booking_id}/
    """
    queryset = Booking.objects.select_related('listing', 'user', 'status')
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    lookup_field = 'booking_id'
    
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status__status_name', 'listing']
    ordering_fields = ['start_date', 'created_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        """
        Use different serializers for different actions
        """
        if self.action == 'create':
            return BookingCreateSerializer
        return BookingSerializer

    def get_queryset(self):
        """
        Filter bookings to show only user's own bookings
        unless they are the property host
        """
        user = self.request.user
        
        # Get bookings where user is either the guest or the host
        return Booking.objects.filter(
            models.Q(user=user) | models.Q(listing__host=user)
        ).distinct()

    def perform_create(self, serializer):
        """
        Set the user to the current user when creating a booking
        """
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def confirm(self, request, booking_id=None):
        """
        Confirm a booking (host only)
        Endpoint: POST /api/bookings/{booking_id}/confirm/
        """
        booking = self.get_object()
        
        # Only the host can confirm bookings
        if request.user != booking.listing.host:
            return Response(
                {'error': 'Only the host can confirm bookings'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update booking status
        confirmed_status = BookingStatus.objects.get(status_name='confirmed')
        booking.status = confirmed_status
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, booking_id=None):
        """
        Cancel a booking
        Endpoint: POST /api/bookings/{booking_id}/cancel/
        """
        booking = self.get_object()
        
        # Only the guest or host can cancel
        if request.user not in [booking.user, booking.listing.host]:
            return Response(
                {'error': 'You do not have permission to cancel this booking'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update booking status
        cancelled_status = BookingStatus.objects.get(status_name='cancelled')
        booking.status = cancelled_status
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def my_bookings(self, request):
        """
        Get all bookings for the current user (as guest)
        Endpoint: GET /api/bookings/my_bookings/
        """
        bookings = Booking.objects.filter(user=request.user)
        serializer = self.get_serializer(bookings, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def hosting_bookings(self, request):
        """
        Get all bookings for properties hosted by the current user
        Endpoint: GET /api/bookings/hosting_bookings/
        """
        bookings = Booking.objects.filter(listing__host=request.user)
        serializer = self.get_serializer(bookings, many=True)
        return Response(serializer.data)


class ReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Review model.
    Provides CRUD operations for reviews.
    """
    queryset = Review.objects.select_related('listing', 'user')
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]
    lookup_field = 'review_id'

    def perform_create(self, serializer):
        """
        Set the user to the current user when creating a review
        """
        serializer.save(user=self.request.user)



class PaymentInitiateView(CreateAPIView):
    serializer_class = PaymentSerializer
    queryset = Payment.objects.all()

    def perform_create(self, serializer):
        """
        Create payment initiation.
        """
        payment_method_data = self.request.data.get('payment_method') # {"payment_method": {"method_name": "Chapa", "method_id": "some-uuid"}} // note method_id is optional and not required
        payment_method, _ = PaymentMethod.objects.get_or_create(**payment_method_data)
        booking_id = self.kwargs.get('booking_id')
        booking = get_object_or_404(Booking, booking_id=booking_id)

        instance = serializer.save(user=self.request.user, booking=booking, payment_method=payment_method)

        return instance

    def create(self, request, *args, **kwargs):
        """
        Override create to initialize payment with Chapa
        """
        response = super().create(request, *args, **kwargs)

        if (response.status_code != status.HTTP_201_CREATED):
            return response
        booking = response.data['booking']
        payment_id = response.data['payment_id']
        payment_instance = Payment.objects.get(payment_id=payment_id)

        # Initialize payment with Chapa

        # Generate unique transaction reference
        tx_ref = f"booking-{booking['booking_id']}-{uuid.uuid4().hex[:8]}"

        chapa_service = ChapaService()
        callback_url = request.build_absolute_uri('/api/payments/webhook/')
        return_url = request.build_absolute_uri(f'/payments/status/{tx_ref}/')

        chapa_response = chapa_service.initialize_payment(
            booking=booking,
            user=request.user,
            callback_url=callback_url,
            return_url=return_url
        )

        if chapa_response['status'] == 'success':
            # Update payment instance with chapa_reference
            payment_instance.chapa_reference = chapa_response['tx_ref']
            payment_instance.save()

            return Response({
                'status': chapa_response['status'],
                'checkout_url': chapa_response['checkout_url'],
                'data': chapa_response['data'],
                'tx_ref': chapa_response['tx_ref'],
                'message': chapa_response['message']
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(
                {'error': 'Failed to initialize payment with Chapa', 'details': chapa_response.get('message', '')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
class PaymentStatusView(APIView):
    """
    View to verify payment status.
    """

    def get(self, request, tx_ref):
        chapa_service = ChapaService()
        verification_response = chapa_service.get_payment_status(tx_ref)
        payment_data = verification_response['data']
        try:
            payment_instance = Payment.objects.select_related(
                'booking', 'booking__user', 'booking__listing'
            ).get(chapa_reference=tx_ref)

            if (verification_response['status'] == 'success'):
                return Response({
                    'status': verification_response['status'],
                    'payment_status': payment_instance.payment_status,
                    'payment_data': payment_data,
                    'message': 'Payment verified successfully'
                }, status=status.HTTP_200_OK)
            else:
                logger.error(f"Payment verification failed for tx_ref {tx_ref}: {verification_response.get('message', '')}")
                return Response(
                            {'error': 'Failed to verify payment', 'details': verification_response.get('message', '')},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )

        except Payment.DoesNotExist:
            return Response(
                {'error': 'Payment record not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error verifying payment status: {str(e)}")
            return Response(
                {'error': 'An error occurred while verifying payment status'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PaymentWebhookView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        """
        Handle payment webhook from Chapa
        """
        chapa_service = ChapaService()
        webhook_data = request.data

        try:
            response = chapa_service.handle_webhook(webhook_data)
            payment_instance = Payment.objects.get(chapa_reference=webhook_data.get('tx_ref'))
            payment_instance.payment_status = "completed" if webhook_data['status'] == "success" else "failed" if webhook_data['status'] == "failed/cancelled" else webhook_data['status'] if webhook_data['status'] in ['refunded', 'reversed'] else  "pending"
            payment_instance.transaction_id = webhook_data['reference']
            payment_instance.save()

            # Send confirmation email asynchronously
            if webhook_data['status'] == 'success':
                send_payment_confirmation_email.delay(payment_instance)
            elif webhook_data['status'] == 'failed':
                send_payment_failed_email.delay(payment_instance)

            return Response(response, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return Response(
                {'error': 'An error occurred while processing the webhook'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

class PaymentListView(ListAPIView):
    """
    View to list all payments
    """
    queryset = Payment.objects.select_related('booking', 'user', 'payment_method')
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def filter_queryset(self, queryset):
        """
        Restricts the returned payments to a given user,
        by filtering against a `user_id` query parameter in the URL.
        """

        user = self.request.user

        return queryset.filter(user=user)


class PaymentDetailView(RetrieveAPIView):
    """
    View to retrieve a specific payment
    """
    queryset = Payment.objects.select_related('booking', 'user', 'payment_method')
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'payment_id'

    def get_object(self):
        """
        Retrieves the payment object ensuring it belongs to the requesting user
        """
        obj = super().get_object()
        if obj.user != self.request.user:
            raise PermissionDenied("You do not have permission to access this payment.")
        return obj
    