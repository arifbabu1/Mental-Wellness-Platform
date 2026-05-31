// Section Highlighting - Highlights main sections based on current page
document.addEventListener('DOMContentLoaded', function() {
    // Get current page to determine which section to highlight
    function getCurrentPageSection() {
        const currentPath = window.location.pathname;
        
        if (currentPath.includes('/appointments')) {
            return 'appointments';
        } else if (currentPath.includes('/doctors')) {
            return 'doctors';
        } else if (currentPath.includes('/assessment')) {
            return 'assessment';
        } else if (currentPath.includes('/dashboard')) {
            return 'dashboard';
        } else if (currentPath === '/' || currentPath === '') {
            return 'home';
        }
        
        return 'home';
    }
    
    // Highlight the appropriate section based on current page
    function highlightCurrentPageSection() {
        const currentSection = getCurrentPageSection();
        
        // Remove all previous highlights
        const allSections = document.querySelectorAll('.hero-section, .features-section, .assessment-container, .appointments-container, .doctors-container, .dashboard-container');
        allSections.forEach(section => {
            section.classList.remove('section-active');
            section.style.borderLeft = '';
            section.style.boxShadow = '';
            section.style.backgroundColor = '';
        });
        
        // Apply highlighting based on current page
        if (currentSection === 'appointments') {
            highlightHeroSection();
        } else if (currentSection === 'doctors') {
            highlightHeroSection();
        } else if (currentSection === 'assessment') {
            highlightHeroSection();
        } else if (currentSection === 'dashboard') {
            highlightHeroSection();
        } else if (currentSection === 'home') {
            highlightHeroSection();
            highlightFeaturesSection();
        }
    }
    
    // Highlight hero section
    function highlightHeroSection() {
        const heroSection = document.querySelector('.hero-section');
        if (heroSection) {
            heroSection.classList.add('section-active');
            heroSection.style.borderLeft = '4px solid var(--primary-color)';
            heroSection.style.boxShadow = '0 0 20px rgba(8, 161, 247, 0.1)';
            heroSection.style.backgroundColor = 'rgba(8, 161, 247, 0.02)';
            heroSection.style.transition = 'all 0.3s ease';
        }
    }
    
    // Highlight features section
    function highlightFeaturesSection() {
        const featuresSection = document.querySelector('.features-section');
        if (featuresSection) {
            featuresSection.classList.add('section-active');
            featuresSection.style.borderLeft = '4px solid var(--primary-color)';
            featuresSection.style.boxShadow = '0 0 20px rgba(8, 161, 247, 0.1)';
            featuresSection.style.backgroundColor = 'rgba(8, 161, 247, 0.02)';
            featuresSection.style.transition = 'all 0.3s ease';
        }
    }
    
    // Apply highlighting on page load
    highlightCurrentPageSection();
    
    // Re-apply on page changes (for SPA-like behavior)
    let lastPath = window.location.pathname;
    setInterval(() => {
        if (window.location.pathname !== lastPath) {
            lastPath = window.location.pathname;
            setTimeout(highlightCurrentPageSection, 100);
        }
    }, 500);
});

// Add CSS for section highlighting
const sectionStyles = `
<style>
.section-active {
    position: relative;
    animation: sectionGlow 2s ease-in-out;
}

@keyframes sectionGlow {
    0% {
        box-shadow: 0 0 0 rgba(8, 161, 247, 0);
    }
    50% {
        box-shadow: 0 0 30px rgba(8, 161, 247, 0.2);
    }
    100% {
        box-shadow: 0 0 20px rgba(8, 161, 247, 0.1);
    }
}
</style>
`;

// Inject styles
document.head.insertAdjacentHTML('beforeend', sectionStyles);
