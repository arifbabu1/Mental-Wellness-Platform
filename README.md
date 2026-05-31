# Mental Wellness Platform

A comprehensive Django-based mental health consultation platform that provides secure, professional mental health support through video consultations with certified professionals.

## 🌟 Features

### Core Features
- **Smart Assessment System**: Mental health quiz with weighted scoring and recommendations
- **Role-Based Access Control**: Patient, Doctor, and Admin dashboards with specific permissions
- **Secure Video Consultations**: Video calls with privacy controls
- **Payment Integration**: Payment gateway with automatic fee splitting (20% admin commission)
- **Multi-Layer Security**: User authentication and data protection
- **Professional Responsive Design**: Modern UI optimized for all devices (320px to 4K)

### Authentication System
- **Secure Login**: Professional login page with password visibility toggle
- **User Registration**: Complete registration form with validation
- **Role-Based Access**: Separate dashboards for patients, doctors, and administrators
- **Password Security**: Show/hide password functionality with eye icon

### UI/UX Enhancements
- **Fully Responsive Design**: Perfect optimization for all screen sizes
- **1920×1080 Optimization**: Specific targeting for standard desktop resolution
- **Mobile-First Approach**: Progressive enhancement from mobile to desktop
- **Professional Animations**: Smooth transitions and hover effects
- **Glass Morphism Design**: Modern frosted glass effect with backdrop blur
- **Gradient Theme**: Consistent color palette (#08a1f7 and #09e0fe)

### Technical Architecture
- **Backend**: Django (Python)
- **Database**: SQLite with Django ORM
- **Frontend**: HTML/CSS/JavaScript with modern CSS techniques
- **Styling**: Custom CSS with responsive design and animations
- **Icons**: Font Awesome 6.4.0 for professional iconography

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup Instructions

1. **Navigate to Project Directory**
   ```bash
   cd "MentalWellnessPlatform"
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install Dependencies**
   ```bash
   pip install django
   ```

4. **Database Setup**
   ```bash
   # Create database tables
   python manage.py makemigrations
   python manage.py migrate
   ```

5. **Create Superuser**
   ```bash
   python manage.py createsuperuser
   ```
   Follow the prompts to create an admin account.

6. **Populate Assessment Questions**
   ```bash
   python manage.py populate_assessment
   ```

7. **Run Development Server**
   ```b![![alt text](image-1.png)](image.png)ash
   python manage.py runserver
   ```

8. **Access the Application**
   - Open your browser and navigate to: `http://127.0.0.1:8000`
   - Login page: `http://127.0.0.1:8000/accounts/login/`
   - Registration page: `http://127.0.0.1:8000/accounts/register/`
   - Admin panel: `http://127.0.0.1:8000/admin`

## 📁 Project Structure

```
MentalWellnessPlatform/
├── manage.py                    # Django management script
├── wellness_platform/           # Main project configuration
│   ├── __init__.py
│   ├── settings.py             # Django settings
│   ├── urls.py                # Main URL configuration
│   ├── wsgi.py                # WSGI configuration
│   └── asgi.py                # ASGI configuration
├── home/                       # Main application
│   ├── __init__.py
│   ├── admin.py                # Django admin configuration
│   ├── apps.py                # App configuration
│   ├── models.py              # Database models
│   ├── views.py               # View functions
│   ├── urls.py                # App URL configuration
│   ├── management/            # Django management commands
│   │   └── commands/
│   │       └── populate_assessment.py
│   ├── templates/             # HTML templates
│   │   ├── auth/             # Authentication templates
│   │   │   ├── login.html    # Professional responsive login page
│   │   │   └── register.html # Professional responsive registration page
│   │   ├── patient/          # Patient templates
│   │   ├── doctor/           # Doctor templates
│   │   ├── admin/            # Admin templates
│   │   └── home/             # Home templates
│   └── static/               # Static files
│       └── css/
│           └── styles.css     # Main stylesheet with color palette
└── db.sqlite3                # SQLite database file
```

## 🎨 UI/UX Design

### Responsive Design Features
- **Complete Device Coverage**: 320px to 2560px+ screen support
- **Perfect 1920×1080**: Specific optimization for standard desktop
- **Mobile Optimization**: Touch-friendly interfaces
- **Tablet Support**: iPad and Android tablet optimization
- **Nest Hub Compatible**: Smart display optimization

### Color Palette
- **Primary Color**: #08a1f7 (Professional Blue)
- **Secondary Color**: #09e0fe (Cyan Accent)
- **Text Dark**: #2c3e50 (Dark Text)
- **Text Light**: #6c757d (Light Text)
- **Border**: #e9ecef (Light Border)

### Design Elements
- **Glass Morphism**: Frosted glass effect with backdrop blur
- **Gradient Backgrounds**: Modern linear gradients
- **Professional Animations**: Smooth hover states and transitions
- **Icon Integration**: Font Awesome icons throughout
- **Typography**: Inter font family for modern readability

## 🔐 Authentication Features

### Login System
- **Professional Design**: Modern, clean login interface
- **Password Toggle**: Eye icon to show/hide password
- **Form Validation**: Client-side validation with error messages
- **Responsive Layout**: Perfect on all device sizes
- **Hover Effects**: Professional button animations

### Registration System
- **Complete Form**: All necessary user information fields
- **Real-time Validation**: Instant feedback on form inputs
- **Password Confirmation**: Verify password entry
- **Terms Agreement**: Checkbox for terms and conditions
- **Mobile Optimized**: Touch-friendly form elements

## 📊 Assessment System

### Smart Scoring Algorithm
- **Weighted Questions**: Different weights for different categories
- **Dynamic Recommendations**: Based on assessment results
- **Stress Level Classification**: Low, Moderate, High, Severe categories
- **Professional UI**: Clean assessment interface

## 💰 Payment System

### Payment Integration (Commented for Future)
- Payment gateway integration code is included but commented out
- Automatic fee splitting calculation
- Transaction tracking and status monitoring

## 🎥 Video Consultation

### Video Features
- Secure consultation rooms
- Unique room names for privacy
- Session management and tracking

## 🔧 Admin Features

### Django Admin Integration
- **User Management**: Manage patients, doctors, and admin users
- **Assessment Management**: View and manage assessment questions and results
- **Appointment Management**: Track all appointments and consultations
- **Payment Tracking**: Monitor payment status and commissions

## 🌐 Browser Compatibility

### Supported Browsers
- **Chrome**: Full support with latest features
- **Firefox**: Full support with modern CSS
- **Safari**: Full support including mobile
- **Edge**: Full support with Chromium engine
- **Mobile Browsers**: iOS Safari, Chrome Mobile

### Responsive Breakpoints
- **Desktop**: 1920×1080, 1600px, 1440px, 1366px, 1280px
- **Tablet**: 1024px, 768px
- **Mobile**: 600px, 480px, 400px, 360px, 320px

## 🚀 Future Enhancements

### Planned Features
- [ ] OTP verification system (code included but commented)
- [ ] Payment gateway integration
- [ ] Advanced analytics dashboard
- [ ] Mobile app development
- [ ] Multi-language support
- [ ] Advanced reporting system
- [ ] Dark mode theme
- [ ] Accessibility improvements

## 📞 Support

### Emergency Contacts
- **Emergency Hotline**: 16101
- **Email**: support@mentalwellness.com

## 🤝 Contributing

We welcome contributions to Mental Wellness Platform!

### Development Guidelines
- Follow Django best practices
- Write clean, maintainable code
- Update documentation
- Test responsive design on multiple devices
- Follow accessibility guidelines

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Django Framework for the robust backend
- Modern CSS techniques for responsive design
- Font Awesome for professional icons
- Mental health professionals for domain expertise

---

**Made with ❤️ for mental wellness**

Mental Wellness Platform © 2026 All rights reserved.
