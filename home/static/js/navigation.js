// Navigation Active State Handler
document.addEventListener('DOMContentLoaded', function() {
    // Get current path
    const currentPath = window.location.pathname;
    
    // Get all navigation links
    const navLinks = document.querySelectorAll('.navbar-nav a');
    
    // Function to check if link matches current path
    function isLinkActive(href, path) {
        // Remove trailing slashes for comparison
        const cleanHref = href.replace(/\/$/, '');
        const cleanPath = path.replace(/\/$/, '');
        
        // Exact match
        if (cleanHref === cleanPath) {
            return true;
        }
        
        // Check for partial matches (for dashboard pages)
        if (cleanPath.includes('/dashboard') && cleanHref.includes('/dashboard')) {
            return true;
        }
        
        // Check for specific page matches
        if (cleanPath.includes('/assessment') && cleanHref.includes('/assessment')) {
            return true;
        }
        
        if (cleanPath.includes('/doctors') && cleanHref.includes('/doctors')) {
            return true;
        }
        
        if (cleanPath.includes('/appointments') && cleanHref.includes('/appointments')) {
            return true;
        }
        
        if (cleanPath.includes('/login') && cleanHref.includes('/login')) {
            return true;
        }
        
        if (cleanPath.includes('/register') && cleanHref.includes('/register')) {
            return true;
        }
        
        return false;
    }
    
    // Remove existing active classes
    navLinks.forEach(link => {
        link.classList.remove('active');
    });
    
    // Add active class to current page link
    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href && isLinkActive(href, currentPath)) {
            link.classList.add('active');
        }
    });
    
    // Handle assessment answer selections
    const answerOptions = document.querySelectorAll('.answer-option input[type="radio"]');
    
    answerOptions.forEach(radio => {
        // Add change event listener
        radio.addEventListener('change', function() {
            // Remove any existing selection highlights from this question
            const questionCard = this.closest('.question-card');
            const allOptions = questionCard.querySelectorAll('.answer-option');
            
            allOptions.forEach(option => {
                option.classList.remove('selected');
            });
            
            // Add selected class to the chosen option
            this.closest('.answer-option').classList.add('selected');
        });
        
        // Check if already selected (for page refresh scenarios)
        if (radio.checked) {
            radio.closest('.answer-option').classList.add('selected');
        }
    });
    
    // Add hover effects for better UX
    navLinks.forEach(link => {
        link.addEventListener('mouseenter', function() {
            if (!this.classList.contains('active')) {
                this.style.transform = 'translateY(-1px)';
            }
        });
        
        link.addEventListener('mouseleave', function() {
            if (!this.classList.contains('active')) {
                this.style.transform = 'translateY(0)';
            }
        });
    });
    
});

// Assessment form progress tracking
function updateAssessmentProgress() {
    const totalQuestions = document.querySelectorAll('.question-card').length;
    const answeredQuestions = document.querySelectorAll('.answer-option input[type="radio"]:checked').length;
    
    if (totalQuestions > 0) {
        const progress = (answeredQuestions / totalQuestions) * 100;
        
        // Update progress bar if it exists
        const progressBar = document.querySelector('.progress-bar-fill');
        if (progressBar) {
            progressBar.style.width = progress + '%';
        }
        
        // Update progress text if it exists
        const progressText = document.querySelector('.progress-text');
        if (progressText) {
            progressText.textContent = `Progress: ${answeredQuestions} / ${totalQuestions} questions answered`;
        }
    }
}

// Call progress update when any answer is selected
document.addEventListener('DOMContentLoaded', function() {
    const answerOptions = document.querySelectorAll('.answer-option input[type="radio"]');
    
    answerOptions.forEach(radio => {
        radio.addEventListener('change', updateAssessmentProgress);
    });
    
    // Initial progress update
    updateAssessmentProgress();
});
