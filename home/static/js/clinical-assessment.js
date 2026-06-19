/**
 * 🧠 Clinical Assessment JavaScript
 * PHQ-9 + GAD-7 Interactive Assessment
 */

// Global variables
let totalQuestions = 16;
let answeredQuestions = new Set();
let emergencyRiskDetected = false;

// Initialize assessment
document.addEventListener('DOMContentLoaded', function() {
    initializeAssessment();
    setupFormValidation();
    startSessionTimer();
});

function initializeAssessment() {
    // Set total questions
    document.getElementById('progress-total').textContent = totalQuestions;
    
    // Add change listeners to all radio buttons
    const radioButtons = document.querySelectorAll('input[type="radio"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {
            handleAnswerChange(this);
        });
    });
    
    // Initialize progress
    updateProgress();
}

function handleAnswerChange(radioInput) {
    const questionCard = radioInput.closest('.question-card');
    const questionId = radioInput.name;
    
    // Mark question as answered
    answeredQuestions.add(questionId);
    
    // Add answered class to question card
    questionCard.classList.add('answered');
    
    // Update progress
    updateProgress();
    
    // Check for emergency risk (PHQ-9 Question 9)
    if (questionId === 'phq9_9') {
        checkEmergencyRisk();
    }
    
    // Enable submit button if all questions are answered
    checkSubmitButton();
}

function updateProgress() {
    // Count answered questions
    answeredQuestions.clear();
    const allRadios = document.querySelectorAll('input[type="radio"]:checked');
    
    allRadios.forEach(radio => {
        answeredQuestions.add(radio.name);
    });
    
    const answeredCount = answeredQuestions.size;
    const progressPercentage = (answeredCount / totalQuestions) * 100;
    
    // Update progress bar
    const progressFill = document.getElementById('progress-fill');
    const progressCurrent = document.getElementById('progress-current');
    
    progressFill.style.width = progressPercentage + '%';
    progressCurrent.textContent = answeredCount;
    
    // Add progress animation
    if (progressPercentage === 100) {
        progressFill.style.background = 'linear-gradient(135deg, #28a745, #20c997)';
    }
}

function checkEmergencyRisk() {
    // Check PHQ-9 Question 9 (suicide risk)
    const phq9_q9 = document.querySelector('input[name="phq9_9"]:checked');
    
    if (phq9_q9) {
        const value = parseInt(phq9_q9.value);
        
        if (value >= 2) {
            emergencyRiskDetected = true;
            showEmergencyWarning();
        }
    }
}

function showEmergencyWarning() {
    // Create emergency warning banner
    const warningBanner = document.createElement('div');
    warningBanner.className = 'emergency-warning-banner';
    warningBanner.innerHTML = `
        <div class="warning-content">
            <div class="warning-icon">
                <i class="fas fa-exclamation-triangle"></i>
            </div>
            <div class="warning-text">
                <h4>⚠️ Immediate Support Recommended</h4>
                <p>Based on your response to question 9, we recommend reaching out to a mental health professional immediately.</p>
            </div>
            <div class="warning-actions">
                <button onclick="showEmergencyModal()" class="btn-warning">
                    <i class="fas fa-phone"></i> Get Help Now
                </button>
            </div>
        </div>
    `;
    
    // Insert after header
    const header = document.querySelector('.assessment-header');
    header.parentNode.insertBefore(warningBanner, header.nextSibling);
    
    // Add warning styles
    const warningStyles = `
        .emergency-warning-banner {
            background: linear-gradient(135deg, #ff4757, #ff6348);
            color: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 15px rgba(255, 71, 87, 0.3);
            animation: pulseWarning 2s infinite;
        }
        
        .warning-content {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        
        .warning-icon {
            width: 50px;
            height: 50px;
            background: rgba(255,255,255,0.2);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3rem;
        }
        
        .warning-text h4 {
            margin-bottom: 5px;
            font-size: 1.2rem;
        }
        
        .warning-text p {
            opacity: 0.9;
            line-height: 1.4;
        }
        
        .btn-warning {
            background: white;
            color: #ff4757;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        @keyframes pulseWarning {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.02); }
        }
        
        @media (max-width: 768px) {
            .warning-content {
                flex-direction: column;
                text-align: center;
            }
        }
    `;
    
    // Add styles to head
    const styleSheet = document.createElement('style');
    styleSheet.textContent = warningStyles;
    document.head.appendChild(styleSheet);
}

function checkSubmitButton() {
    const submitBtn = document.getElementById('submit-btn');
    
    if (answeredQuestions.size === totalQuestions) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-chart-line"></i><span>Get My Results</span>';
    } else {
        submitBtn.disabled = true;
        const remaining = totalQuestions - answeredQuestions.size;
        submitBtn.innerHTML = `<i class="fas fa-clock"></i><span>Complete ${remaining} more question${remaining > 1 ? 's' : ''}</span>`;
    }
}

function setupFormValidation() {
    const form = document.getElementById('clinical-assessment-form');
    
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        if (answeredQuestions.size !== totalQuestions) {
            alert('Please answer all questions before submitting.');
            return;
        }
        
        // Show loading state
        const submitBtn = document.getElementById('submit-btn');
        const originalContent = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Analyzing your responses...</span>';
        
        // Submit form
        setTimeout(() => {
            form.submit();
        }, 1500);
    });
}

function startSessionTimer() {
    const startTime = Date.now();
    
    // Update session duration every 10 seconds
    setInterval(() => {
        const duration = Math.floor((Date.now() - startTime) / 1000);
        const minutes = Math.floor(duration / 60);
        const seconds = duration % 60;
        
    }, 10000);
}

// Keyboard navigation
document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        const focusedElement = document.activeElement;
        
        // If focused on a radio button, move to next question
        if (focusedElement.type === 'radio') {
            e.preventDefault();
            moveToNextQuestion(focusedElement);
        }
    }
});

function moveToNextQuestion(currentRadio) {
    const currentQuestion = currentRadio.closest('.question-card');
    const allQuestions = Array.from(document.querySelectorAll('.question-card'));
    const currentIndex = allQuestions.indexOf(currentQuestion);
    
    if (currentIndex < allQuestions.length - 1) {
        const nextQuestion = allQuestions[currentIndex + 1];
        const firstRadio = nextQuestion.querySelector('input[type="radio"]');
        
        if (firstRadio) {
            firstRadio.focus();
            // Scroll to next question
            nextQuestion.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
}

// Smooth scroll to questions
document.querySelectorAll('.question-card').forEach((card, index) => {
    card.addEventListener('click', function(e) {
        // Don't scroll if clicking on a radio button
        if (e.target.type === 'radio' || e.target.tagName === 'LABEL') {
            return;
        }
        
        // Scroll question into view
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
});

// Auto-save progress (optional enhancement)
function autoSaveProgress() {
    const progress = {
        answered: Array.from(answeredQuestions),
        timestamp: Date.now(),
        emergency_risk: emergencyRiskDetected
    };
    
    // Save to localStorage
    localStorage.setItem('clinical_assessment_progress', JSON.stringify(progress));
}

// Load saved progress (optional enhancement)
function loadSavedProgress() {
    const saved = localStorage.getItem('clinical_assessment_progress');
    
    if (saved) {
        try {
            const progress = JSON.parse(saved);
            
            // Check if progress is recent (within 24 hours)
            const hoursSinceSave = (Date.now() - progress.timestamp) / (1000 * 60 * 60);
            
            if (hoursSinceSave < 24) {
                // Restore answered questions
                progress.answered.forEach(questionName => {
                    const radio = document.querySelector(`input[name="${questionName}"]:checked`);
                    if (radio) {
                        handleAnswerChange(radio);
                    }
                });
                
                // Restore emergency risk
                emergencyRiskDetected = progress.emergency_risk;
                if (emergencyRiskDetected) {
                    showEmergencyWarning();
                }
            }
        } catch (e) {
            console.error('Error loading saved progress:', e);
        }
    }
}

// Auto-save every 30 seconds
setInterval(autoSaveProgress, 30000);

// Load saved progress on page load
loadSavedProgress();
