// Mobile Navbar Toggle - Professional Implementation
(function() {
    'use strict';
    
    function initMobileNavbar() {
        const navbarToggle = document.querySelector('.navbar-toggle');
        const navbarNav = document.getElementById('navbarNav');
        
        if (!navbarToggle || !navbarNav) {
            return;
        }
        
        let isMenuOpen = false;
        
        // Toggle function
        function toggleMenu(e) {
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            
            isMenuOpen = !isMenuOpen;
            
            if (isMenuOpen) {
                navbarNav.style.display = 'flex';
                // Small delay to allow display:flex to apply before adding active class for animation
                setTimeout(function() {
                    navbarNav.classList.add('active');
                    navbarToggle.classList.add('active');
                }, 10);
            } else {
                navbarNav.classList.remove('active');
                navbarToggle.classList.remove('active');
                // Delay hiding the display
                setTimeout(function() {
                    if (!isMenuOpen) {
                        navbarNav.style.display = '';
                    }
                }, 300);
            }
        }
        
        // Close function
        function closeMenu() {
            if (!isMenuOpen) return;
            
            isMenuOpen = false;
            navbarNav.classList.remove('active');
            navbarToggle.classList.remove('active');
            setTimeout(function() {
                if (!isMenuOpen) {
                    navbarNav.style.display = '';
                }
            }, 300);
        }
        
        // Toggle button click handler - use both click and touchend for mobile
        navbarToggle.addEventListener('click', toggleMenu);
        navbarToggle.addEventListener('touchend', function(e) {
            e.preventDefault();
            toggleMenu(e);
        });
        
        // Close when clicking nav links on mobile
        const navLinks = navbarNav.querySelectorAll('a');
        navLinks.forEach(function(link) {
            link.addEventListener('click', function() {
                if (window.innerWidth <= 768) {
                    closeMenu();
                }
            });
        });
        
        // Close when clicking outside
        document.addEventListener('click', function(e) {
            if (isMenuOpen && !navbarNav.contains(e.target) && !navbarToggle.contains(e.target)) {
                closeMenu();
            }
        });
        
        // Close on escape key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && isMenuOpen) {
                closeMenu();
            }
        });
        
        // Handle window resize
        window.addEventListener('resize', function() {
            if (window.innerWidth > 768 && isMenuOpen) {
                closeMenu();
            }
        });
        
        // Make toggle available globally
        window.toggleNavbar = toggleMenu;
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initMobileNavbar);
    } else {
        initMobileNavbar();
    }
})();
