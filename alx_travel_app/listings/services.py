"""
Chapa Payment Gateway Integration Service
"""
import requests
from django.conf import settings
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class ChapaService:
    """
    Service class for integrating with Chapa Payment Gateway
    """
    
    # Chapa API URLs
    SANDBOX_BASE_URL = "https://api.chapa.co/v1"
    PRODUCTION_BASE_URL = "https://api.chapa.co/v1"
    
    def __init__(self):
        """Initialize Chapa service with API credentials"""
        self.secret_key = settings.CHAPA_SECRET_KEY
        self.base_url = self.SANDBOX_BASE_URL if settings.DEBUG else self.PRODUCTION_BASE_URL
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json'
        }
    
    def initialize_payment(self, booking, user, tx_ref, callback_url, return_url):
        """
        Initialize a payment transaction with Chapa
        
        Args:
            booking: Booking data dictionary from the payment creation.
            user: User object making the payment
            callback_url: URL for Chapa to send webhook notifications
            return_url: URL to redirect user after payment
            
        Returns:
            dict: Response from Chapa API containing checkout_url and tx_ref
        """
        # retrieve all the information from the booking dictionary

        booking_id = booking['booking_id']
        property_name = booking['listing']['name']
        start_date = booking['start_date']
        end_date = booking['end_date']
        total_price = booking['total_price']

        
        # Prepare payment data
        payment_data = {
            "amount": str(total_price),
            "currency": "NGN",  
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number or "",
            "tx_ref": tx_ref,
            "callback_url": callback_url,
            "return_url": return_url,
            "customization": {
                "title": f"Booking Payment - {property_name}",
                "description": f"Payment for booking from {start_date} to {end_date}",
            }
        }
        
        try:
            # Make API request to Chapa
            response = requests.post(
                f"{self.base_url}/transaction/initialize",
                json=payment_data,
                headers=self.headers,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Payment initialized for booking {booking_id}: {tx_ref}")
            
            return {
                'status': 'success',
                'data': result.get('data', {}),
                'tx_ref': tx_ref,
                'checkout_url': result.get('data', {}).get('checkout_url'),
                'message': result.get('message', 'Payment initialized successfully')
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Chapa API error during payment initialization: {str(e)}")
            return {
                'status': 'error',
                'message': f'Payment initialization failed: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error during payment initialization: {str(e)}")
            return {
                'status': 'error',
                'message': f'An unexpected error occurred: {str(e)}'
            }
    
    def verify_payment(self, tx_ref):
        """
        Verify payment status with Chapa
        
        Args:
            tx_ref: Transaction reference from Chapa
            
        Returns:
            dict: Payment verification response
        """
        try:
            response = requests.get(
                f"{self.base_url}/transaction/verify/{tx_ref}",
                headers=self.headers,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            logger.info(f"Payment verification for {tx_ref}: {result.get('status')}")
            
            return {
                'status': 'success',
                'data': result.get('data', {}),
                'message': result.get('message', 'Payment verified successfully')
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Chapa API error during payment verification: {str(e)}")
            return {
                'status': 'error',
                'message': f'Payment verification failed: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Unexpected error during payment verification: {str(e)}")
            return {
                'status': 'error',
                'message': f'An unexpected error occurred: {str(e)}'
            }
    
    def get_payment_status(self, tx_ref):
        """
        Get the status of a payment transaction
        
        Args:
            tx_ref: Transaction reference
            
        Returns:
            str: Payment status (success, pending, failed)
        """
        verification_result = self.verify_payment(tx_ref)
        
        # if verification_result['status'] == 'success':
        #     data = verification_result.get('data', {})
        #     return data.get('status', 'pending')
        
        # return 'failed'
        return verification_result
    
    def handle_webhook(self, webhook_data):
        """
        Handle webhook notification from Chapa
        
        Args:
            webhook_data: Data received from Chapa webhook
            
        Returns:
            dict: Processed webhook data
        """
        try:
            tx_ref = webhook_data.get('tx_ref')
            status = webhook_data.get('status')
            
            logger.info(f"Webhook received for {tx_ref}: {status}")
            
            # Verify the transaction
            verification = self.verify_payment(tx_ref)
            
            return {
                'status': 'success',
                'tx_ref': tx_ref,
                'payment_status': status,
                'verification': verification
            }
            
        except Exception as e:
            logger.error(f"Error handling webhook: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def get_banks(self):
        """
        Get list of supported banks (for bank transfer payments)
        
        Returns:
            dict: List of banks
        """
        try:
            response = requests.get(
                f"{self.base_url}/banks",
                headers=self.headers,
                timeout=30
            )
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching banks: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
        



class EmailService:
    """
    Service class for sending emails
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags

    @staticmethod
    def send_email(subject, to_email, html_message):
        """
        Send an email using a template
        
        Args:
            subject: Email subject
            to_email: Recipient email address
            template_name: Template file name
            context: Context data for rendering the template
            
        Returns:
            None
        """
        plain_message = EmailService.strip_tags(html_message)
        
       
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[to_email],
            html_message=html_message,
            fail_silently=False,
        )