# ALX Travel App

A Django REST API application for managing travel listings, bookings, and reviews.

## Project Overview

This project implements a travel booking platform similar to Airbnb, with the following features:

- User authentication and management
- Property listings management
- Booking system
- Review and rating system
- Payment tracking
- Messaging between users

### New Features added
- Configure and run Celery with RabbitMQ as a message broker.
- Create and manage shared tasks in Django using Celery.
- Trigger Celery tasks from Django views or viewsets.
- Test and verify asynchronous operations such as sending emails.

## Technology Stack

- **Backend**: Django 4.2.7 + Django REST Framework
- **Database**: MySQL
- **API Documentation**: drf-spectacular (OpenAPI 3.0)
- **Task Queue**: Celery with RabbitMq