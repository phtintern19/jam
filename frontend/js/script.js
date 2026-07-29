// --- Theme Toggling Logic ---
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const icons = document.querySelectorAll('.theme-icon');
    icons.forEach(icon => {
        if (theme === 'light') {
            icon.classList.remove('fa-moon');
            icon.classList.add('fa-sun');
        } else {
            icon.classList.remove('fa-sun');
            icon.classList.add('fa-moon');
        }
    });
}

// Initialize theme immediately
initTheme();
// -----------------------------

// Function to fetch events from API
async function fetchEvents() {
    const loadingEvents = document.getElementById('loadingEvents');
    const eventsGrid = document.getElementById('eventsGrid');

    try {
        console.log('Fetching events from API...');
        const response = await fetch('/api/events');

        if (!response.ok) {
            let errorMessage = `HTTP error! status: ${response.status}`;
            try {
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorMessage;
                } else {
                    const errorText = await response.text();
                    console.error('Non-JSON error response:', errorText);
                    errorMessage = `Server returned non-JSON response (Status: ${response.status})`;
                }
            } catch (parseError) {
                console.error('Error parsing error response:', parseError);
            }
            throw new Error(errorMessage);
        }

        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response from /api/events:', text);
            throw new Error('Server returned non-JSON response. Please check if the backend is running correctly.');
        }

        const events = await response.json();
        console.log('Fetched events:', events);

        // Convert array to object keyed by ID for compatibility
        window.eventsData = {};
        events.forEach(event => {
            window.eventsData[event.event_id] = event;
        });

        // Render events on home page
        renderHomePageEvents(events);

        return events;
    } catch (error) {
        console.error('Error fetching events:', error);
        window.eventsData = {};

        // Hide loading spinner
        if (loadingEvents) {
            loadingEvents.style.display = 'none';
        }

        // Show error message in the grid
        if (eventsGrid) {
            eventsGrid.innerHTML = `
                <div class="col-span-full text-center py-10">
                    <i class="fas fa-exclamation-triangle text-4xl text-red-500 mb-4"></i>
                    <p class="text-gray-600 font-medium">Unable to load live events</p>
                    <p class="text-sm text-gray-400 mt-2">Error: ${error.message}</p>
                    <button class="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition" onclick="fetchEvents()">
                        <i class="fas fa-sync-alt mr-2"></i> Try Again
                    </button>
                </div>
            `;
        }
    }
}

// Function to render events on home page
function renderHomePageEvents(events) {
    const eventsGrid = document.querySelector('.events-grid');
    if (!eventsGrid) return; // Not on home page

    // Hide loading spinner
    const loadingEvents = document.getElementById('loadingEvents');
    if (loadingEvents) {
        loadingEvents.style.display = 'none';
    }

    // Set grid class to our new redesigned grid
    eventsGrid.className = 'ecr-grid';
    eventsGrid.innerHTML = '';

    if (events.length === 0) {
        eventsGrid.innerHTML = '<p class="no-events">No upcoming events found.</p>';
        return;
    }

    // Color palettes for headers (Image 0 match)
    const colorSchemes = [
        { main: '#4338ca', secondary: '#4f46e5' }, // Deep Blue (ecr-card)
        { main: '#f59e0b', secondary: '#fbbf24' }, // Warm Orange
        { main: '#10b981', secondary: '#34d399' }, // Vibrant Green
        { main: '#6366f1', secondary: '#818cf8' }, // Indigo
        { main: '#f43f5e', secondary: '#fb7185' }  // Rose
    ];

    events.forEach((event, index) => {
        const colorScheme = colorSchemes[index % colorSchemes.length];
        const date = new Date(event.start_date);
        const dateStr = date.toLocaleDateString('en-US', {
            month: 'long',
            day: 'numeric',
            year: 'numeric'
        });

        const card = document.createElement('div');
        card.className = 'ecr-card';
        card.setAttribute('data-aos', 'fade-up');

        let statusText = 'Upcoming';
        if (event.is_live) statusText = 'Live Now';

        let sportsHtml = '';
        if (event.sports && event.sports.length > 0) {
            event.sports.slice(0, 5).forEach(sport => {
                sportsHtml += `<span class="saas-card-sport-tag">${sport.name}</span>`;
            });
            if (event.sports.length > 5) {
                sportsHtml += `<span class="saas-card-sport-tag">+${event.sports.length - 5}</span>`;
            }
        } else {
            sportsHtml = '<span class="saas-card-sport-tag" style="background: rgba(148, 163, 184, 0.1); border-color: rgba(148, 163, 184, 0.2); color: #94a3b8;">All Sports Categories</span>';
        }

        const registrationFee = event.registration_fee ? `₹${event.registration_fee.toLocaleString()}` : 'Free';

        card.innerHTML = `
            <div class="saas-card-badge">${statusText}</div>
            
            <h3 class="saas-card-title">${event.title}</h3>
            
            <div class="saas-card-sports">
                ${sportsHtml}
            </div>
            
            <div class="saas-card-meta">
                <div class="saas-meta-item">
                    <span class="saas-meta-label">Date</span>
                    <span class="saas-meta-val"><i class="fas fa-calendar"></i> ${dateStr}</span>
                </div>
                <div class="saas-meta-item">
                    <span class="saas-meta-label">Location</span>
                    <span class="saas-meta-val"><i class="fas fa-map-marker-alt"></i> ${event.location || 'TBA'}</span>
                </div>
                <div class="saas-meta-item">
                    <span class="saas-meta-label">Entry Fee</span>
                    <span class="saas-meta-val"><i class="fas fa-ticket-alt"></i> ${registrationFee}</span>
                </div>
                <div class="saas-meta-item">
                    <span class="saas-meta-label">Prize Pool</span>
                    <span class="saas-meta-val"><i class="fas fa-trophy"></i> TBD</span>
                </div>
                <div class="saas-meta-item" style="grid-column: span 2;">
                    <span class="saas-meta-label">Registered Teams</span>
                    <span class="saas-meta-val"><i class="fas fa-users"></i> ${event.current_participants || 0} / ${event.max_players || event.max_participants || '∞'} Teams</span>
                </div>
            </div>
            
            <div class="saas-card-footer">
                <button class="saas-btn-primary w-full" onclick="showEventDetails(${event.event_id})">View Details</button>
            </div>
        `;


        eventsGrid.appendChild(card);
    });

    // Check for live auction section and update it
    updateLiveAuctionSection(events);
}

function updateLiveAuctionSection(events) {
    const liveSection = document.getElementById('live-auctions');
    if (!liveSection) return;

    const liveEvents = events.filter(e => e.is_live);
    if (liveEvents.length > 0) {
        liveSection.style.display = 'block';
        // Logic to populate live auction carousel could go here
    } else {
        liveSection.style.display = 'none';
    }
}

// Function to show event details modal
// Function to show event details modal
window.showEventDetails = function (eventId) {
    const event = window.eventsData[eventId];
    if (!event) return;

    const modal = document.getElementById('eventDetailsModal');
    const content = document.getElementById('eventDetailsDynamicContent');
    if (!modal || !content) return;

    const startDate = new Date(event.start_date);
    const endDate = new Date(event.end_date);
    const deadline = event.registration_deadline ? new Date(event.registration_deadline) : null;

    const isDeadlinePassed = deadline && new Date() > deadline;

    // Formatting
    const formatDateTime = (date) => {
        return date.toLocaleDateString('en-US', {
            day: 'numeric',
            month: 'long',
            year: 'numeric'
        }) + ' at ' + date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    let sportsListHtml = '';
    if (event.sports && event.sports.length > 0) {
        event.sports.forEach(sport => {
            sportsListHtml += `<div class="saas-card-sport-tag">${sport.name}</div>`;
        });
    } else {
        sportsListHtml = '<p style="color: #64748b;">No sports specified</p>';
    }

    content.innerHTML = `
        <div class="event-details-header-banner">
            <span class="status-badge">${event.is_live ? 'Live Now' : 'Upcoming'}</span>
            <h2>${event.title}</h2>
            <p class="event-details-description">${event.description || 'Join the most prestigious sports combine event where top talent meets opportunity.'}</p>
        </div>

        <div class="registration-status-bar">
            <div class="status-labels">
                <span><i class="fas fa-users"></i> Registration Status</span>
                <span>0 / ${event.max_players || 200} participants registered</span>
            </div>
            <div class="progress-container">
                <div class="progress-fill" style="width: 2%;"></div>
            </div>
        </div>

        <div class="details-grid-section">
            <div class="details-card">
                <h4><i class="fas fa-wallet"></i> Budget Information</h4>
                <div class="total-budget-display">
                    <div class="total-budget-label">Total Budget</div>
                    <div class="total-budget-value">₹${event.budget ? event.budget.toLocaleString() : '50,00,000'}</div>
                </div>
                <div class="budget-info-grid">
                    <div class="budget-tier gold">
                        <span class="tier-label">Gold</span>
                        <span class="tier-value">₹${event.base_prices?.gold?.toLocaleString() || '50,000'}</span>
                    </div>
                    <div class="budget-tier silver">
                        <span class="tier-label">Silver</span>
                        <span class="tier-value">₹${event.base_prices?.silver?.toLocaleString() || '25,000'}</span>
                    </div>
                    <div class="budget-tier diamond">
                        <span class="tier-label">Diamond</span>
                        <span class="tier-value">₹${event.base_prices?.diamond?.toLocaleString() || '1,00,000'}</span>
                    </div>
                    <div class="budget-tier platinum">
                        <span class="tier-label">Platinum</span>
                        <span class="tier-value">₹${event.base_prices?.platinum?.toLocaleString() || '75,000'}</span>
                    </div>
                </div>
            </div>

            <div class="details-card">
                <h4><i class="fas fa-calendar-alt"></i> Date & Time</h4>
                <div class="meta-item" style="margin-bottom: 1rem;">
                    <i class="fas fa-play-circle"></i>
                    <div>
                        <div style="font-size: 0.8rem; color: #64748b;">Start</div>
                        <div>${formatDateTime(startDate)}</div>
                    </div>
                </div>
                <div class="meta-item" style="margin-bottom: 1rem;">
                    <i class="fas fa-stop-circle"></i>
                    <div>
                        <div style="font-size: 0.8rem; color: #64748b;">End</div>
                        <div>${formatDateTime(endDate)}</div>
                    </div>
                </div>
                <div class="meta-item">
                    <i class="fas fa-clock"></i>
                    <div>
                        <div style="font-size: 0.8rem; color: #64748b;">Registration Deadline</div>
                        <div>${deadline ? formatDateTime(deadline) : 'TBA'}</div>
                    </div>
                </div>
            </div>

            <div class="details-card">
                <h4><i class="fas fa-map-marker-alt"></i> Location</h4>
                <div class="meta-item" style="margin-bottom: 1rem;">
                    <i class="fas fa-map-marker-alt"></i>
                    <span>${event.location || event.city + ', ' + event.state || 'TBA'}</span>
                </div>
                <div class="meta-item">
                    <i class="fas fa-home"></i>
                    <span>${event.address || 'Address TBA'}</span>
                </div>
            </div>

            <div class="details-card">
                <h4><i class="fas fa-running"></i> Sports Categories</h4>
                <div class="event-card-sports">
                    ${sportsListHtml}
                </div>
            </div>

            <div class="details-card">
                <h4><i class="fas fa-gavel"></i> Auction Settings</h4>
                <div class="meta-item" style="margin-bottom: 1rem;">
                    <i class="fas fa-hourglass-half"></i>
                    <span>Bid Time Limit: ${event.bid_time_limit || 20} seconds</span>
                </div>
                <div class="meta-item">
                    <i class="fas fa-users"></i>
                    <span>Max Participants: ${event.max_players || 200}</span>
                </div>
                <div class="meta-item" style="margin-top: 1rem;">
                    <i class="fas fa-users-cog"></i>
                    <span>Max Teams: ${event.max_teams || 'TBA'}</span>
                </div>
            </div>

            ${event.extra_info ? `
            <div class="details-card" style="grid-column: 1 / -1;">
                <h4><i class="fas fa-info-circle"></i> Extra Information</h4>
                <div class="event-details-description" style="margin-bottom: 0; background: #0f172a; padding: 1.5rem; border-radius: 12px; border: 1px solid #334155;">
                    ${event.extra_info}
                </div>
            </div>
            ` : ''}
        </div>

        <div class="event-details-footer">
            ${isDeadlinePassed
            ? `<div class="deadline-passed-badge"><i class="fas fa-exclamation-circle"></i> Registration Deadline Passed</div>`
            : `<button class="register-btn-main" onclick="closeModal('eventDetailsModal'); handleRegisterClick(event, ${event.event_id})">Register Now</button>`
        }
            <button class="back-btn" onclick="closeModal('eventDetailsModal')">Back to Events</button>
        </div>
    `;

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
}
    ;

// Initialize
// showAuthModal function to open login, registration, or staff registration modal
// This function handles the parent-child staff registration flow
window.showAuthModal = function (mode) {
    if (mode === 'register') {
        const regModal = document.getElementById('playerRegistrationModal');
        if (regModal) {
            closeAllModals();
            regModal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        }
    } else if (mode === 'staffRegistrationModal') {
        // Open staff registration modal for invited team manager/analyst
        // This is part of the parent-child relationship flow
        const staffModal = document.getElementById('staffRegistrationModal');
        if (staffModal) {
            closeAllModals();
            staffModal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        }
    } else {
        showLoginModal();
    }
    return false;
};

// Initialize immediately to handle dynamic script loading
fetchEvents();

document.addEventListener('DOMContentLoaded', function () {
    // Already called above, but keeping for safety if loaded traditionally
    if (!window.eventsData || Object.keys(window.eventsData).length === 0) {
        fetchEvents();
    }
});

// Original eventsData stub removed, replaced by fetchEvents


// Global error handler to catch any JavaScript errors
window.addEventListener('error', function (event) {
    console.error('Global JavaScript error:', event.error);
    console.error('Error details:', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno
    });
});

// Global unhandled promise rejection handler
window.addEventListener('unhandledrejection', function (event) {
    console.error('Unhandled promise rejection:', event.reason);
});

// For backward compatibility
const eventsData = window.eventsData;

// Mobile Navigation Toggle
document.addEventListener('DOMContentLoaded', function () {
    try {
        console.log('DOM loaded - initializing all components');
        console.log('Current URL:', window.location.href);
        console.log('Page title:', document.title);
        console.log('Body content length:', document.body.innerHTML.length);

        // Check if main content exists
        const mainSections = document.querySelectorAll('section');
        console.log('Found sections:', mainSections.length);

        // Mobile menu toggle
        const hamburger = document.querySelector('.hamburger');
        const navMenu = document.querySelector('.nav-menu');

        console.log('Hamburger element:', hamburger);
        console.log('Nav menu element:', navMenu);

        if (hamburger && navMenu) {
            hamburger.addEventListener('click', function () {
                navMenu.classList.toggle('active');
                hamburger.classList.toggle('active');
            });
        }

        // Smooth scrolling for navigation links
        const navLinks = document.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', function (e) {
                e.preventDefault();
                const targetId = this.getAttribute('href');
                const targetSection = document.querySelector(targetId);
                if (targetSection) {
                    targetSection.scrollIntoView({ behavior: 'smooth' });
                }
            });
        });

        // Add event listener for team owner registration form
        const teamOwnerForm = document.getElementById('teamOwnerRegistrationForm');
        if (teamOwnerForm) {
            teamOwnerForm.addEventListener('submit', handleTeamOwnerRegistration);
        }

        // Handle click events on register buttons using event delegation
        document.addEventListener('click', function (event) {
            // Check if the clicked element is a register button or a child of one
            const registerBtn = event.target.closest('.register-btn');
            if (registerBtn) {
                event.preventDefault();
                const eventId = registerBtn.getAttribute('data-event-id') || 1;
                handleRegisterClick(event, eventId);
            }
        });

        // Check for registration parameter in URL
        const urlParams = new URLSearchParams(window.location.search);
        const registerEventId = urlParams.get('register');

        if (registerEventId) {
            // Remove the parameter from URL without refreshing
            window.history.replaceState({}, document.title, window.location.pathname);

            // Open registration modal for the specific event
            setTimeout(() => {
                registerForEvent(registerEventId);
            }, 500);
        }

        // Card hover effects
        const cards = document.querySelectorAll('.ecr-card, .event-card, .role-card');
        cards.forEach(card => {
            card.addEventListener('mouseenter', function () {
                this.style.transform = 'translateY(-8px)';
            });

            card.addEventListener('mouseleave', function () {
                this.style.transform = 'translateY(0)';
            });
        });

        // Initialize pulse effect
        addLivePulseEffect();

        // Initialize any forms
        if (typeof initializeForms === 'function') {
            initializeForms();
        }

    } catch (error) {
        console.error('Error during DOM initialization:', error);
    }
});

// Admin and Team Owner credentials (In a real app, this would be handled by a secure backend)
const adminCredentials = {
    username: 'admin',
    password: 'admin123',
    type: 'admin',
    name: 'System Administrator'
};

const teamOwners = [
    {
        username: 'owner1',
        password: 'owner123',
        type: 'team_owner',
        name: 'Rajesh Sharma',
        teamName: 'Mumbai Warriors',
        email: 'owner@mumbaiwarriors.com',
        phone: '+91 98765 43210',
        walletBalance: 1500000,
        squad: []
    },
    {
        username: 'owner2',
        password: 'owner456',
        type: 'team_owner',
        name: 'Priya Patel',
        teamName: 'Delhi Dynamos',
        email: 'owner@delhidynamos.com',
        phone: '+91 87654 32109',
        walletBalance: 2200000,
        squad: []
    }
];

// Show login modal
function showLoginModal() {
    adminLogActivity('Login Modal Opened', 'User clicked Sign In button', 'admin');
    closeAllModals();
    document.getElementById('loginModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

// Show team owner registration modal
async function showTeamOwnerRegistration() {
    adminLogActivity('Team Owner Registration Started', 'User clicked Register as Team Owner button', 'team_owner');
    closeAllModals();

    // Dynamically populate the events dropdown before showing
    await populateRegistrationDropdown();

    document.getElementById('teamOwnerRegistrationForm').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

// Populate the event registration dropdown dynamically
async function populateRegistrationDropdown() {
    const dropdown = document.getElementById('teamOwnerEvent');
    if (!dropdown) return;

    // Clear existing options except the first one
    while (dropdown.options.length > 1) {
        dropdown.remove(1);
    }

    // Ensure we have eventsData
    let events = [];
    if (window.eventsData && Object.keys(window.eventsData).length > 0) {
        events = Object.values(window.eventsData);
    } else {
        console.log('No events in window.eventsData, fetching...');
        events = await fetchEvents();
    }

    if (events && events.length > 0) {
        events.forEach(event => {
            const option = document.createElement('option');
            option.value = event.event_id;
            // Show [LIVE] prefix for live events
            const prefix = event.is_live ? '[LIVE] ' : '';
            option.textContent = `${prefix}${event.title}`;
            dropdown.appendChild(option);
        });
        console.log(`Populated dropdown with ${events.length} events`);
    } else {
        console.warn('No events found to populate dropdown');
    }
}

// Close all auth modals
function closeAllModals() {
    const modals = document.querySelectorAll('.modal-overlay');
    modals.forEach(modal => {
        modal.style.display = 'none';
    });
    document.body.style.overflow = '';
}

// Close specific modal
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
        document.body.style.overflow = '';

        // Also clear form when closing player registration
        if (modalId === 'playerRegistrationModal') {
            const form = document.getElementById('playerRegistrationForm');
            if (form) form.reset();
        }
    }
}

// Make functions globally available
window.closeModal = closeModal;

// Handle Register Click from Event Details
window.handleRegisterClick = async function (event, eventId) {
    if (event) event.preventDefault();
    console.log('Register clicked for event:', eventId);

    const modal = document.getElementById('playerRegistrationModal');
    const form = document.getElementById('playerRegistrationForm');

    if (modal && form) {
        // Store event ID in form dataset
        form.dataset.eventId = eventId;

        // Reset form and clear previous ratings
        form.reset();
        const ratingsContainer = document.getElementById('sportRatingsContainer');
        const ratingsInputs = document.getElementById('sportRatingsInputs');

        if (ratingsContainer && ratingsInputs) {
            ratingsInputs.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Loading sports...</div>';
            ratingsContainer.style.display = 'block';

            try {
                // Fetch sports for the event
                const response = await fetch(`/api/events/${eventId}/sports`);
                if (response.ok) {
                    const sports = await response.json();
                    ratingsInputs.innerHTML = ''; // Clear loading

                    if (sports && sports.length > 0) {
                        sports.forEach(sport => {
                            const ratingItem = document.createElement('div');
                            ratingItem.className = 'sport-rating-item';
                            ratingItem.innerHTML = `
                                <div class="rating-label">
                                    <span class="sport-name"><i class="${sport.icon_class || 'fas fa-trophy'}"></i> ${sport.name}</span>
                                    <span class="rating-value" id="rating-val-${sport.sport_id}">0</span>
                                </div>
                                <input type="range" 
                                    class="sport-rating-input" 
                                    id="rating-${sport.sport_id}" 
                                    data-sport-id="${sport.sport_id}" 
                                    data-sport-name="${sport.name}"
                                    min="0" max="10" value="0" step="1"
                                    oninput="document.getElementById('rating-val-${sport.sport_id}').textContent = this.value">
                                <div class="rating-scale">
                                    <span>No Exp</span>
                                    <span>Expert</span>
                                </div>
                            `;
                            ratingsInputs.appendChild(ratingItem);
                        });
                    } else {
                        ratingsInputs.innerHTML = '<p class="text-muted">No specific sports linked to this event.</p>';
                    }
                } else {
                    console.error('Failed to fetch sports');
                    ratingsInputs.innerHTML = '<p class="error-text">Failed to load sports.</p>';
                }
            } catch (error) {
                console.error('Error fetching sports:', error);
                ratingsInputs.innerHTML = '<p class="error-text">Error loading sports.</p>';
            }
        }

        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    } else {
        console.error('Player registration modal not found');
        window.location.href = '/register';
    }
};

// Make functions globally available
window.closeModal = closeModal;
window.showTeamOwnerRegistration = showTeamOwnerRegistration;
// window.showAuthModal already defined at top level

// Close auth modal (login or staff registration)
// This function handles closing both login modal and staff registration modal
window.closeAuthModal = function (modalId) {
    // If modalId is provided, close that specific modal
    if (modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }
        return false;
    }
    
    // Default behavior: close login modal
    const modal = document.getElementById('loginModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }
    return false;
};

// Handle role change in login form
function handleRoleChange() {
    const roleSelect = document.getElementById('role');
    const passwordGroup = document.getElementById('passwordGroup');
    const passwordInput = document.getElementById('password');
    const usernameLabel = document.getElementById('usernameLabel');
    const usernameInput = document.getElementById('username');
    const loginSubmitBtn = document.getElementById('loginSubmitBtn');
    const staffSetupGroup = document.getElementById('staffSetupGroup');
    const mainLoginForm = document.getElementById('mainLoginForm');
    const rememberForgotGroup = document.getElementById('rememberForgotGroup');

    if (roleSelect && passwordGroup) {
        const selectedRole = roleSelect.value;
        
        // Reset state
        mainLoginForm.dataset.staffStep = "1";
        staffSetupGroup.style.display = 'none';
        
        if (selectedRole === 'team_manager' || selectedRole === 'team_analyst') {
            // For Staff: Hide password initially, change to Email only check
            passwordGroup.style.display = 'none';
            passwordInput.required = false;
            usernameLabel.textContent = 'Email Address';
            usernameInput.placeholder = 'Enter your email address';
            loginSubmitBtn.innerHTML = '<i class="fas fa-arrow-right"></i><span>Continue</span>';
            rememberForgotGroup.style.display = 'none';
        } else {
            // For others: Standard login
            passwordGroup.style.display = 'block';
            passwordInput.required = true;
            usernameLabel.textContent = 'Username or Email';
            usernameInput.placeholder = 'Enter your username or email';
            loginSubmitBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i><span>Sign In</span>';
            rememberForgotGroup.style.display = 'flex';
        }
    }
}

// Handle login form submission with role selection
async function handleLogin(event) {
    event.preventDefault();
    console.log('Login form submitted');

    const form = document.getElementById('mainLoginForm');
    const usernameInput = document.getElementById('username') || document.getElementById('loginEmail');
    const passwordInput = document.getElementById('password') || document.getElementById('loginPassword');
    const roleInput = document.getElementById('role');
    const rememberMeInput = document.getElementById('remember') || document.getElementById('rememberMe');

    const username = usernameInput ? usernameInput.value.trim() : '';
    let password = passwordInput ? passwordInput.value : '';
    const role = roleInput ? roleInput.value : 'player';
    const rememberMe = rememberMeInput ? rememberMeInput.checked : false;

    // Handle Staff specific multi-step logic
    if (role === 'team_manager' || role === 'team_analyst') {
        const step = form.dataset.staffStep || "1";
        
        if (step === "1") {
            if (!username) {
                showModal('Error', 'Please enter your email address.');
                return false;
            }
            
            // Check invitation
            try {
                const btn = document.getElementById('loginSubmitBtn');
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Checking...</span>';
                
                const res = await fetch('/api/staff/check-invitation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: username })
                });
                const data = await res.json();
                
                if (!data.has_invitation) {
                    showModal('Error', data.message || 'No account found with this email.');
                    btn.innerHTML = '<i class="fas fa-arrow-right"></i><span>Continue</span>';
                    return false;
                }
                
                if (data.status === 'pending') {
                    // Show setup password fields
                    document.getElementById('staffSetupGroup').style.display = 'block';
                    document.getElementById('staffNewPassword').required = true;
                    document.getElementById('staffConfirmPassword').required = true;
                    
                    document.getElementById('staffInvitationInfo').innerHTML = `You have been invited as ${data.role} by ${data.team_owner_name}. Please set your password.`;
                    
                    form.dataset.staffStep = "2_setup";
                    btn.innerHTML = '<i class="fas fa-check"></i><span>Complete Setup</span>';
                } else {
                    // Already registered, just show normal password field
                    document.getElementById('passwordGroup').style.display = 'block';
                    passwordInput.required = true;
                    document.getElementById('rememberForgotGroup').style.display = 'flex';
                    
                    form.dataset.staffStep = "2_login";
                    btn.innerHTML = '<i class="fas fa-sign-in-alt"></i><span>Sign In</span>';
                }
            } catch (err) {
                showModal('Error', 'An error occurred while checking your email.');
                document.getElementById('loginSubmitBtn').innerHTML = '<i class="fas fa-arrow-right"></i><span>Continue</span>';
            }
            return false;
        } else if (step === "2_setup") {
            const newPwd = document.getElementById('staffNewPassword').value;
            const confirmPwd = document.getElementById('staffConfirmPassword').value;
            if (!newPwd || !confirmPwd) {
                showModal('Error', 'Please fill in both password fields.');
                return false;
            }
            if (newPwd !== confirmPwd) {
                showModal('Error', 'Passwords do not match.');
                return false;
            }
            if (newPwd.length < 6) {
                showModal('Error', 'Password must be at least 6 characters.');
                return false;
            }
            
            try {
                const btn = document.getElementById('loginSubmitBtn');
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Registering...</span>';
                
                const res = await fetch('/api/staff/complete-registration', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: username, password: newPwd })
                });
                const data = await res.json();
                
                if (data.success) {
                    if (data.session_token) {
                        document.cookie = `session_token=${data.session_token}; path=/; max-age=86400`;
                    }
                    localStorage.setItem('user', JSON.stringify(data.user));
                    window.location.href = data.redirect_to || '/team-owner-dashboard.html';
                } else {
                    showModal('Error', data.message || 'Registration failed.');
                    btn.innerHTML = '<i class="fas fa-check"></i><span>Complete Setup</span>';
                }
            } catch (err) {
                showModal('Error', 'An error occurred during registration.');
                document.getElementById('loginSubmitBtn').innerHTML = '<i class="fas fa-check"></i><span>Complete Setup</span>';
            }
            return false;
        }
        // If step is "2_login", it will fall through to standard login using the password field
    }

    // Basic validation for standard login
    if (!username || !password) {
        showModal('Error', 'Please enter both username/email and password.');
        return false;
    }

    // Log the login attempt
    console.log('Attempting to login with username:', username, 'role:', role);

    const btn = document.getElementById('loginSubmitBtn');
    const originalBtnHTML = btn ? btn.innerHTML : '';
    if(btn) btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Signing in...</span>';

    // Send login request to backend with role parameter
    fetch('/api/login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json; charset=utf-8',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        },
        cache: 'no-store',
        body: JSON.stringify({
            username: username,
            password: password,
            role: role,
            remember_me: rememberMe
        })
    })
        .then(response => {
            console.log('Response status:', response.status);
            if (!response.ok) {
                return response.text().then(text => {
                    console.error('Error response:', text);
                    try {
                        const data = JSON.parse(text);
                        throw new Error(data.detail || 'Login failed');
                    } catch (e) {
                        throw new Error(text || 'Login failed');
                    }
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Login successful:', data);
            console.log('Redirect path:', data.redirect_to);
            console.log('User role:', data.user?.role);
            console.log('User type:', data.user?.user_type);
            
            if (data.success) {
                // Store user info in localStorage
                localStorage.setItem('user', JSON.stringify(data.user));
                localStorage.setItem('session_token', data.session_token);
                
                // Redirect to the unified dashboard. rbac-router.js will handle SPA routing to /dashboard/manager, etc.
                let redirectPath = data.redirect_to || '/team-owner-dashboard.html';
                const userRole = data.user.role || data.user.user_type;
                if (['team_owner', 'team_manager', 'team_analyst'].includes(userRole)) {
                    redirectPath = '/team-owner-dashboard.html';
                }
                console.log('Redirecting to unified dashboard:', redirectPath);
                
                // Small delay to ensure localStorage is set
                setTimeout(() => {
                    window.location.href = redirectPath;
                }, 100);
            } else {
                showModal('Error', data.message || 'Login failed');
            }
        })
        .catch(error => {
            console.error('Login error:', error);
            console.error('Error details:', error.message);
            showModal('Error', error.message || 'Login failed. Please try again.');
        });

    return false;
}

// Password validation function
function validatePasswordStrength(password) {
    const requirements = {
        length: password.length >= 8,
        uppercase: /[A-Z]/.test(password),
        number: /[0-9]/.test(password),
        special: /[!@#$%^&*()]/.test(password)
    };

    const strength = Object.values(requirements).filter(Boolean).length;
    const strengthBar = document.querySelector('#passwordStrength .strength-bar');
    const strengthText = document.querySelector('#passwordStrength .strength-text span');

    if (strengthBar && strengthText) {
        const strengthPercent = (strength / 4) * 100;
        strengthBar.style.width = strengthPercent + '%';

        if (strength === 0) {
            strengthBar.style.backgroundColor = '#ff4444';
            strengthText.textContent = 'Very Weak';
        } else if (strength === 1) {
            strengthBar.style.backgroundColor = '#ff6644';
            strengthText.textContent = 'Weak';
        } else if (strength === 2) {
            strengthBar.style.backgroundColor = '#ffaa44';
            strengthText.textContent = 'Fair';
        } else if (strength === 3) {
            strengthBar.style.backgroundColor = '#44ff44';
            strengthText.textContent = 'Good';
        } else {
            strengthBar.style.backgroundColor = '#44ff88';
            strengthText.textContent = 'Strong';
        }
    }

    return strength === 4;
}

// Handle successful login
function handleSuccessfulLogin(user, rememberMe) {
    console.log('Login successful for user:', user);

    // Set session data
    sessionStorage.setItem('isAuthenticated', 'true');
    sessionStorage.setItem('user_type', user.user_type);
    sessionStorage.setItem('username', user.username);
    sessionStorage.setItem('user_id', user.user_id);
    sessionStorage.setItem('email', user.email);

    if (rememberMe) {
        // Store in localStorage for persistent login
        localStorage.setItem('user_type', user.user_type);
        localStorage.setItem('username', user.username);
        localStorage.setItem('user_id', user.user_id);
        localStorage.setItem('email', user.email);
    } else {
        // Clear any existing persistent data
        localStorage.removeItem('user_type');
        localStorage.removeItem('username');
        localStorage.removeItem('user_id');
        localStorage.removeItem('email');
    }

    console.log('Session storage after login:', {
        isAuthenticated: sessionStorage.getItem('isAuthenticated'),
        user_type: sessionStorage.getItem('user_type'),
        username: sessionStorage.getItem('username'),
        user_id: sessionStorage.getItem('user_id')
    });

    // Log team owner login to admin activity log
    if (user.type === 'team_owner') {
        adminLogActivity('Team Owner Login', `Username: ${user.username}${user.teamName ? ", Team: " + user.teamName : ''}`, 'team_owner');
    }
    // Log user login activity
    if (user.user_type) {
        adminLogActivity(
            `${user.user_type.charAt(0).toUpperCase() + user.user_type.slice(1)} Login`,
            `Username: ${user.username}`,
            user.user_type
        );
    }

    // Show success message
    const welcomeMessage = user.user_type === 'admin'
        ? `Welcome back, ${user.username || 'Admin'}!`
        : `Welcome, ${user.username || 'User'}!`;

    showModal('Login Successful', welcomeMessage);
    console.log('Login successful, user data:', user); // Debug log

    // Redirect to appropriate dashboard based on user type
    console.log('Preparing to redirect to dashboard...');
    setTimeout(() => {
        if (!user.user_type) {
            console.error('User type not found in response');
            showModal('Error', 'Unable to determine user type. Please contact support.');
            return;
        }

        const dashboards = {
            'admin': 'admin-dashboard.html',
            'player': 'player-dashboard.html',
            'team_owner': 'team-owner-dashboard.html'
        };

        const dashboard = dashboards[user.user_type];
        if (dashboard) {
            console.log(`Redirecting to ${user.user_type} dashboard...`);
            window.location.href = dashboard;
        } else {
            console.error('Unknown user type:', user.user_type);
            showModal('Error', `Unknown user type: ${user.user_type}. Please contact support.`);
        }
    }, 1500);
}

// Check if user is logged in and has required role
function checkAuth(requiredRole = null) {
    const isAuthenticated = sessionStorage.getItem('isAuthenticated') === 'true';
    const userType = sessionStorage.getItem('user_type');

    if (!isAuthenticated) {
        // Try to restore from localStorage if available
        const savedUserType = localStorage.getItem('user_type');
        const savedUsername = localStorage.getItem('username');
        const savedUserId = localStorage.getItem('user_id');

        if (savedUserType && savedUsername && savedUserId) {
            // Restore session from localStorage
            sessionStorage.setItem('isAuthenticated', 'true');
            sessionStorage.setItem('user_type', savedUserType);
            sessionStorage.setItem('username', savedUsername);
            sessionStorage.setItem('user_id', savedUserId);

            console.log('Session restored from localStorage');

            // If we have a required role, check against it
            if (requiredRole && savedUserType !== requiredRole) {
                console.warn(`User does not have required role: ${requiredRole}`);
                return false;
            }
            return true;
        }
        return false;
    }

    // If a specific role is required, check it
    if (requiredRole && userType !== requiredRole) {
        console.warn(`User does not have required role: ${requiredRole}`);
        return false;
    }

    return true;
}

// Logout function
function logout() {
    // Capture details before clearing for logging
    const userType = sessionStorage.getItem('user_type');
    const username = sessionStorage.getItem('username');
    const userId = sessionStorage.getItem('user_id');

    // Log user logout activity
    if (userType) {
        adminLogActivity(
            `${userType.charAt(0).toUpperCase() + userType.slice(1)} Logout`,
            `User logged out: ${username} (ID: ${userId})`,
            userType
        );
    }
    if (userType === 'team_owner') {
        adminLogActivity('Team Owner Logout', `Username: ${username}${teamName ? ", Team: " + teamName : ''}`, 'team_owner');
    }
    // Log admin logout
    if (userType === 'admin') {
        adminLogActivity('Admin Logout', `Username: ${username}`, 'admin');
    }
    // Log player logout
    if (userType === 'player') {
        adminLogActivity('Player Logout', `Username: ${username}`, 'player');
    }

    // Call backend to invalidate session
    fetch('/api/logout', { method: 'POST' })
        .then(() => console.log('Session invalidated on server'))
        .catch(err => console.error('Error invalidating session:', err))
        .finally(() => {
            sessionStorage.removeItem('isAuthenticated');
            sessionStorage.removeItem('user_type');
            sessionStorage.removeItem('username');
            sessionStorage.removeItem('user_id');
            sessionStorage.removeItem('email');

            localStorage.removeItem('user_type');
            localStorage.removeItem('username');
            localStorage.removeItem('user_id');
            localStorage.removeItem('email');

            window.location.href = '/index.html';
        });
}


// Helper: write to admin activity log in localStorage (shared with admin dashboard)
function adminLogActivity(action, details) {
    try {
        const key = 'adminActivityLogs';
        const logs = JSON.parse(localStorage.getItem(key) || '[]');
        logs.push({ timestamp: new Date().toISOString(), action, details });
        // Keep last 500 entries max
        const trimmed = logs.slice(-500);
        localStorage.setItem(key, JSON.stringify(trimmed));
    } catch (e) {
        // Swallow errors to avoid blocking auth flow
        console.warn('Failed to write admin activity log:', e);
    }

    // Also send activity to backend so it is stored in the database
    try {
        fetch('/api/activity-logs/public', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action_type: action,
                action_description: details || '',
                entity_type: null,
                entity_id: null,
                ip_address: null,
                user_agent: navigator.userAgent
            })
        }).catch(err => {
            console.warn('Failed to send shared activity log to server:', err);
        });
    } catch (err) {
        console.warn('Failed to send shared activity log to server:', err);
    }
}

// Global click logger: send generic activity logs for interactive element clicks to backend
function sendGlobalClickLog(event) {
    try {
        const interactiveTarget = event.target && event.target.closest && event.target.closest('button, a, input[type="button"], input[type="submit"]');
        if (!interactiveTarget) {
            return;
        }

        const text = (interactiveTarget.innerText || interactiveTarget.value || '').trim();
        const ariaLabel = interactiveTarget.getAttribute('aria-label') || '';
        const dataAction = interactiveTarget.getAttribute('data-action') || '';

        const actionLabel = dataAction || ariaLabel || text || interactiveTarget.id || interactiveTarget.className || 'UI Click';
        const truncatedAction = actionLabel.length > 80 ? actionLabel.slice(0, 77) + '...' : actionLabel;

        const details = `Page: ${window.location.pathname}, Tag: ${interactiveTarget.tagName}, id: ${interactiveTarget.id || ''}, classes: ${interactiveTarget.className || ''}`;

        fetch('/api/activity-logs/public', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action_type: truncatedAction,
                action_description: details,
                entity_type: null,
                entity_id: null,
                ip_address: null,
                user_agent: navigator.userAgent
            })
        }).catch(err => {
            console.warn('Failed to send global click activity log to server:', err);
        });
    } catch (err) {
        console.warn('Error in global click logger:', err);
    }
}

// Attach global click listener for all pages (non-intrusive, keeps existing handlers intact)
document.addEventListener('click', sendGlobalClickLog, true);

// Sample player data removed - enforcing DB usage

// Function to show player registration with sports ratings
function showPlayerRegistration(eventId) {
    adminLogActivity('Player Registration Started', `User opened player registration modal for event ${eventId || ''}`, 'player');
    // Show the registration modal
    const modal = document.getElementById('playerRegistrationModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

    }
}

// Function to show a generic modal with title and message
function showModal(title, message) {
    const modal = document.getElementById('genericModal');
    const modalTitle = document.getElementById('genericModalTitle');
    const modalDescription = document.getElementById('genericModalDescription');

    if (modal && modalTitle && modalDescription) {
        modalTitle.textContent = title;
        modalDescription.innerHTML = message; // Use innerHTML to support <br> or other basic tags
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    }
}

// Function to update sports ratings based on selected event (removed - skill rating section deleted)
function updateSportsRatings(eventId) {
    // Skill rating section has been removed from the form
    return;
}

function updateSkillsRating(eventId) {
    // Skill rating section has been removed from the form
    return;
}

// Function to reset player registration form
function resetPlayerRegistrationForm() {
}

// eventsData will be populated dynamically by fetchEvents


// Handle register button clicks
function handleRegisterClick(event, eventId) {
    try {
        // Prevent default form submission and stop propagation
        if (event) {
            if (typeof event.preventDefault === 'function') {
                event.preventDefault();
            }
            if (typeof event.stopPropagation === 'function') {
                event.stopPropagation();
            }
        }

        // Get the target element that triggered the event
        const target = event ? (event.target || event.srcElement) : null;

        // If eventId is not provided, try to get it from the button's data attribute
        if (!eventId && target) {
            const button = target.closest('.register-btn');
            if (button) {
                eventId = button.getAttribute('data-event-id');
            }
        }

        // Convert eventId to number and ensure it's valid
        eventId = parseInt(eventId, 10) || 1;

        console.log('Registering for event:', eventId);

        // Close any open modals
        if (typeof closeAllModals === 'function') {
            closeAllModals();
        }

        // Show the registration modal
        const modal = document.getElementById('playerRegistrationModal');
        if (!modal) {
            console.error('Registration modal not found');
            return;
        }

        // Set the event ID in the form
        const form = document.getElementById('playerRegistrationForm');
        if (form) {
            form.dataset.eventId = eventId;
        }

        // Update the modal title
        const eventName = (window.eventsData && window.eventsData[eventId])
            ? window.eventsData[eventId].title
            : 'Event';

        const modalHeader = modal.querySelector('.modal-header h2');
        if (modalHeader) {
            modalHeader.textContent = `Register for ${eventName}`;
        }

        // Show the modal
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        // Load sports ratings for this event
        if (typeof loadSportRatingsForEvent === 'function') {
            loadSportRatingsForEvent(eventId);
        }
    } catch (error) {
        console.error('Error in handleRegisterClick:', error);
        // Optionally show an error message to the user
        alert('An error occurred while processing your request. Please try again.');
    }
}

// Make the function available globally
window.handleRegisterClick = handleRegisterClick;

// Password strength validation function
function validatePasswordStrength(password) {
    // Check if password contains at least one letter and one number
    const hasLetter = /[a-zA-Z]/.test(password);
    const hasNumber = /[0-9]/.test(password);
    return hasLetter && hasNumber;
}

// Handle Team Owner Registration Form Submission
async function handleTeamOwnerRegistration(event) {
    event.preventDefault();

    const form = document.getElementById('teamOwnerForm');
    if (!form) {
        console.error('Team owner registration form not found');
        showModal('Registration Error', 'Registration form not found. Please try again.');
        return false;
    }

    const submitButton = form.querySelector('button[type="submit"]');
    const originalButtonText = submitButton ? submitButton.innerHTML : 'Submit';

    try {
        // Get form values
        const email = form.querySelector('#ownerEmail').value.trim();
        const username = email; // Use email as username
        const phone = form.querySelector('#ownerPhone').value.trim();
        const password = form.querySelector('#ownerPassword').value.trim();
        const confirmPassword = form.querySelector('#ownerConfirmPassword').value.trim();
        const teamName = form.querySelector('#ownerTeamName').value.trim();
        const ownerName = form.querySelector('#ownerName').value.trim();
        const address = form.querySelector('#ownerAddress').value.trim();
        const eventId = form.querySelector('#teamOwnerEvent').value;
        
        // Get staff fields (optional)
        const teamManagerName = form.querySelector('#teamManagerName')?.value.trim() || '';
        const teamManagerEmail = form.querySelector('#teamManagerEmail')?.value.trim() || '';
        const teamAnalystName = form.querySelector('#teamAnalystName')?.value.trim() || '';
        const teamAnalystEmail = form.querySelector('#teamAnalystEmail')?.value.trim() || '';

        // Basic validation
        if (!email || !phone || !password || !confirmPassword || !teamName || !ownerName || !address) {
            showModal('Validation Error', 'Please fill in all required fields.');
            return false;
        }

        // Password validation
        if (password.length < 6) {
            showModal('Validation Error', 'Password must be at least 6 characters long.');
            return false;
        }

        // Password strength validation
        if (!validatePasswordStrength(password)) {
            showModal('Validation Error', 'Password must contain at least one letter and one number.');
            return false;
        }

        // Confirm password validation
        if (password !== confirmPassword) {
            showModal('Validation Error', 'Passwords do not match. Please try again.');
            return false;
        }

        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Registering...';
        }

        // Prepare the data for the API
        const userData = {
            username,
            email,
            phone,
            password,
            user_type: 'team_owner'
        };

        const teamOwnerData = {
            team_name: teamName,
            owner_name: ownerName,
            address: address,
            event_id: eventId ? parseInt(eventId) : null,
            // Staff invitation fields for parent-child relationship
            // These optional fields allow team owner to invite staff (manager/analyst)
            // Backend will create pending user entries linked to this team owner via parent_user_id
            teamManagerName: teamManagerName,
            teamManagerEmail: teamManagerEmail,
            teamAnalystName: teamAnalystName,
            teamAnalystEmail: teamAnalystEmail
        };

        // Combine both data objects
        const registrationData = {
            user_data: userData,
            team_owner_data: teamOwnerData
        };

        // Send the request to the backend
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

        const response = await fetch('/register/team-owner', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(registrationData),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        const data = await response.json();

        if (!response.ok) {
            // Handle the error response format from the backend
            if (data.errors && data.errors.length > 0) {
                throw new Error(data.errors[0] || data.message || 'Registration failed');
            } else if (data.message) {
                throw new Error(data.message);
            } else if (data.detail) {
                throw new Error(data.detail);
            } else {
                throw new Error('Registration failed. Please try again.');
            }
        }

        // Show success message with staff information
        let successMessage = 'Your registration has been submitted successfully!';
        
        // Show staff invitations created
        if (data.staff_invitations && data.staff_invitations.length > 0) {
            successMessage += '\n\nStaff invitations created:\n';
            data.staff_invitations.forEach(inv => {
                successMessage += `\n- ${inv.role}: ${inv.email}`;
            });
            successMessage += '\n\nShare these emails with your team members to complete their registration.';
        }
        
        // Show staff email conflicts as warnings
        if (data.staff_errors && data.staff_errors.length > 0) {
            successMessage += '\n\nStaff Email Conflicts:\n';
            data.staff_errors.forEach(error => {
                successMessage += '\n- ' + error;
            });
            successMessage += '\n\nPlease use different email addresses for these staff members.';
        }
        
        showModal('Registration Submitted', successMessage);

        // Reset form
        form.reset();

        // Close modal after a delay
        setTimeout(() => {
            closeAllModals();
        }, 2000);

    } catch (error) {
        console.error('Registration error:', error);
        showModal('Registration Error', error.message || 'An error occurred during registration. Please try again.');
    } finally {
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = originalButtonText;
        }
    }

    return false;
}

// Handle Staff Invitation Check
// This is the first step in the staff registration flow
// Staff enters their email to check if they have a pending invitation from a team owner
async function handleStaffCheckInvitation(event) {
    event.preventDefault();
    
    const form = document.getElementById('staffCheckForm');
    const email = form.querySelector('#staffEmail').value.trim();
    
    // Validate email input
    if (!email) {
        showModal('Validation Error', 'Please enter your email address.');
        return false;
    }
    
    try {
        // Call backend API to check for pending invitation
        const response = await fetch('/api/staff/check-invitation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email })
        });
        
        const data = await response.json();
        
        // If no invitation found, show error message
        if (!data.has_invitation) {
            showModal('No Invitation Found', data.message || 'No pending invitation found for this email. Please contact your team owner.');
            return false;
        }
        
        // Show invitation details to the user
        // Displays: role (manager/analyst), team owner name
        const invitationInfo = document.getElementById('invitationInfo');
        invitationInfo.innerHTML = `
            <h4 style="margin: 0 0 0.5rem 0; color: #0369a1;">Invitation Found!</h4>
            <p style="margin: 0 0 0.5rem 0; color: #0c4a6e;">You have been invited as <strong>${data.role}</strong></p>
            <p style="margin: 0; color: #0c4a6e;">Team Owner: ${data.team_owner_name}</p>
        `;
        
        // Store email in form dataset for use in completion step
        form.dataset.email = email;
        
        // Switch UI from check step to complete registration step
        document.getElementById('staffCheckStep').style.display = 'none';
        document.getElementById('staffCompleteStep').style.display = 'block';
        
    } catch (error) {
        console.error('Error checking invitation:', error);
        showModal('Error', 'Failed to check invitation. Please try again.');
    }
    
    return false;
}

// Handle Staff Registration Completion
// This is the second step in the staff registration flow
// After invitation is verified, staff sets username and password to activate their account
async function handleStaffCompleteRegistration(event) {
    event.preventDefault();
    
    const checkForm = document.getElementById('staffCheckForm');
    const form = document.getElementById('staffCompleteForm');
    
    // Get email from previous step (stored in dataset)
    const email = checkForm.dataset.email;
    const username = form.querySelector('#staffUsername').value.trim();
    const password = form.querySelector('#staffPassword').value.trim();
    const confirmPassword = form.querySelector('#staffConfirmPassword').value.trim();
    
    // Validate all required fields
    if (!email || !username || !password || !confirmPassword) {
        showModal('Validation Error', 'Please fill in all required fields.');
        return false;
    }
    
    // Validate password length
    if (password.length < 6) {
        showModal('Validation Error', 'Password must be at least 6 characters long.');
        return false;
    }
    
    // Validate password confirmation
    if (password !== confirmPassword) {
        showModal('Validation Error', 'Passwords do not match.');
        return false;
    }
    
    const submitButton = form.querySelector('button[type="submit"]');
    const originalButtonText = submitButton ? submitButton.innerHTML : 'Submit';
    
    try {
        // Disable submit button and show loading state
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Registering...';
        }
        
        // Call backend API to complete registration
        // Backend will: validate invitation, set username/password, activate account
        const response = await fetch('/api/staff/complete-registration', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                email,
                username,
                password,
                confirmPassword
            })
        });
        
        const data = await response.json();
        
        // Handle API errors
        if (!response.ok) {
            throw new Error(data.message || data.detail || 'Registration failed');
        }
        
        // Store session token in cookie for authentication
        if (data.session_token) {
            document.cookie = `session_token=${data.session_token}; path=/; max-age=86400`;
        }
        
        // Show success message
        showModal('Registration Successful', 'Your registration has been completed! You can now log in.');
        
        // Reset form and close modal
        form.reset();
        document.getElementById('staffCheckStep').style.display = 'block';
        document.getElementById('staffCompleteStep').style.display = 'none';
        
        // Redirect to dashboard after short delay
        setTimeout(() => {
            closeAllModals();
            // Redirect to appropriate dashboard based on user type
            // Both manager and analyst currently use team-owner-dashboard
            if (data.user.user_type === 'team_manager') {
                window.location.href = '/team-owner-dashboard.html';
            } else if (data.user.user_type === 'team_analyst') {
                window.location.href = '/team-owner-dashboard.html';
            }
        }, 2000);
        
    } catch (error) {
        console.error('Registration error:', error);
        showModal('Registration Error', error.message || 'An error occurred during registration. Please try again.');
    } finally {
        // Re-enable submit button
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = originalButtonText;
        }
    }
    
    return false;
}

// Add event delegation for register buttons and forms
// DOMContentLoaded consolidated above

// Make the function available globally
window.handleRegisterClick = handleRegisterClick;

// Handle Player Registration Form Submission
// Helper function to handle form submission
async function submitForm(url, data) {
    const headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    };

    // Add auth token if available
    const token = localStorage.getItem('authToken');
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

    const response = await fetch(url, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(data),
        signal: controller.signal
    });

    clearTimeout(timeoutId);

    let responseData;
    try {
        responseData = await response.json();
    } catch (e) {
        // If response is not JSON, use status text
        const error = new Error(response.statusText || 'Request failed');
        error.status = response.status;
        throw error;
    }

    if (!response.ok) {
        let errorMessage = 'Request failed';

        // Handle different types of error responses
        if (responseData) {
            if (typeof responseData.detail === 'string') {
                errorMessage = responseData.detail;
            } else if (Array.isArray(responseData.detail)) {
                errorMessage = responseData.detail
                    .map(err => typeof err === 'object' ?
                        `${err.loc ? err.loc.join('.') + ': ' : ''}${err.msg || JSON.stringify(err)}` :
                        String(err)
                    )
                    .join('\n');
            } else if (typeof responseData.detail === 'object') {
                errorMessage = Object.entries(responseData.detail)
                    .map(([key, value]) => `${key}: ${value}`)
                    .join('\n');
            } else if (responseData.message) {
                errorMessage = responseData.message;
            } else if (responseData.error) {
                errorMessage = responseData.error;
            }
        }

        const error = new Error(errorMessage);
        error.response = responseData;
        error.status = response.status;
        throw error;
    }

    return responseData;
}

// Helper function to validate phone number
function validatePhoneNumber(phone) {
    const phoneRegex = /^[0-9]{10,15}$/;
    return phoneRegex.test(phone);
}

// Event Registration Functions form-section text-center
function openRegistrationModal(eventId) {
    console.log('🚀 openRegistrationModal called with eventId:', eventId);
    const modal = document.getElementById('playerRegistrationModal');

    if (!modal) {
        console.error('❌ Error: playerRegistrationModal not found in the DOM');
        return;
    }

    // Store the event ID for later use
    modal.setAttribute('data-event-id', eventId);

    // Reset form and clear previous data
    const form = document.getElementById('playerRegistrationForm');
    if (form) {
        form.reset();
        // Skill rating section has been removed from the form
        console.log('📝 Form reset completed (skill rating section removed)');
    } else {
        console.error('❌ Error: playerRegistrationForm not found inside modal');
    }

    // Show modal with proper styling
    modal.style.display = 'flex';
    modal.classList.add('active');

    // Focus on first input field
    const firstInput = document.getElementById('playerFirstName');
    if (firstInput) {
        setTimeout(() => firstInput.focus(), 100);
    }

    console.log('[SUCCESS] Modal opened successfully for event:', eventId);

    // Load sport ratings for this event
    if (typeof loadSportRatingsForEvent === 'function') {
        loadSportRatingsForEvent(eventId);
    }
}

function updateSkillsRating(eventId) {
    // Skill rating section has been removed from the form
    return;
}

// Function to collect sports ratings from form
function collectSportsRatings() {
    // Skill rating section has been removed from the form
    return {};
}

// Helper function to show error messages in the UI
function showError(fieldId, message) {
    // Normalize fieldId by removing 'player' prefix if it exists and convert to lowercase
    const normalizedFieldId = fieldId.replace(/^player/, '').toLowerCase();
    const errorElement = document.getElementById(`${normalizedFieldId}Error`);

    if (errorElement) {
        errorElement.textContent = message;
        errorElement.style.display = 'block';
    } else {
        console.warn(`Error element ${normalizedFieldId}Error not found`);
    }
}

// Helper function to clear error messages
function clearError(fieldId) {
    // Normalize fieldId by removing 'player' prefix if it exists and convert to lowercase
    const normalizedFieldId = fieldId.replace(/^player/, '').toLowerCase();
    const errorElement = document.getElementById(`${normalizedFieldId}Error`);

    if (errorElement) {
        errorElement.textContent = '';
        errorElement.style.display = 'none';
    }
}

// Show modal function

async function handlePlayerRegistration(event) {
    event.preventDefault();

    // Get form and submit button
    const form = document.getElementById('playerRegistrationForm');
    if (!form) {
        console.error('Registration form not found');
        showModal('Registration Error', 'Registration form not found. Please try again.');
        return false;
    }

    const submitButton = form.querySelector('button[type="submit"]');
    const originalButtonText = submitButton ? submitButton.innerHTML : 'Submit';

    // Clear previous errors
    ['firstName', 'lastName', 'email', 'phone', 'dob', 'password', 'confirmPassword', 'gender'].forEach(field => {
        clearError(`player${field.charAt(0).toUpperCase() + field.slice(1)}`);
    });

    try {
        // Get form values safely with validation
        const getFormValue = (id, required = true) => {
            try {
                const element = document.getElementById(id);
                if (!element) {
                    console.error(`Element with id '${id}' not found`);
                    if (required) {
                        showError(id, 'This field is required');
                    }
                    return null;
                }

                const value = element.value ? element.value.trim() : '';

                // Validate required fields
                if (required && !value) {
                    showError(id, 'This field is required');
                    return null;
                }

                return value;
            } catch (error) {
                console.error(`Error getting value for ${id}:`, error);
                if (required) {
                    showError(id, 'Error processing this field');
                }
                return null;
            }
        };

        // Get form values
        const firstName = getFormValue('playerFirstName');
        const lastName = getFormValue('playerLastName');
        const email = getFormValue('playerEmail');
        const phone = getFormValue('playerPhone');
        const dob = getFormValue('playerDob');
        const password = getFormValue('playerPassword');
        const confirmPassword = getFormValue('playerConfirmPassword');

        // Validate password requirements
        if (!validatePasswordStrength(password)) {
            showModal('Password Requirements', 'Password must be at least 8 characters long and include:<br>• At least one uppercase letter<br>• At least one number<br>• At least one special character (!@#$%^&*)');
            return false;
        }

        if (password !== confirmPassword) {
            showModal('Password Mismatch', 'Password and confirm password do not match. Please check and try again.');
            return false;
        }

        // Get selected gender with validation
        const genderSelect = document.getElementById('playerGender');
        const genderValue = genderSelect ? genderSelect.value : null;

        if (!genderValue) {
            showError('playerGender', 'Please select a gender');
            return false;
        }

        // Skill rating section has been removed

        // Validate passwords match
        if (password !== confirmPassword) {
            showError('playerConfirmPassword', 'Passwords do not match');
            return false;
        }

        // Validate required fields
        const requiredFields = [
            { id: 'playerFirstName', name: 'First Name' },
            { id: 'playerLastName', name: 'Last Name' },
            { id: 'playerEmail', name: 'Email' },
            { id: 'playerPhone', name: 'Phone' },
            { id: 'playerDob', name: 'Date of Birth' },
            { field: 'gender', name: 'Gender' },
            { id: 'playerPassword', name: 'Password' },
            { id: 'playerConfirmPassword', name: 'Confirm Password' }
        ];

        const missingFields = [];

        requiredFields.forEach(field => {
            const value = field.id ? getFormValue(field.id) : genderValue;
            if (!value) {
                missingFields.push(field.name);
            }
        });

        if (missingFields.length > 0) {
            throw new Error(`Please fill in all required fields: ${missingFields.join(', ')}`);
        }

        // Validate email format
        if (!isValidEmail(email)) {
            showError('playerEmail', 'Please enter a valid email address');
            return;
        }

        // Validate phone number format
        if (!/^[0-9]{10}$/.test(phone)) {
            showError('playerPhone', 'Please enter a valid 10-digit phone number');
            return;
        }

        // Validate date of birth (must be at least 10 years old)
        const dobDate = new Date(dob);
        const today = new Date();
        const minAgeDate = new Date(today.getFullYear() - 10, today.getMonth(), today.getDate());

        if (dobDate > minAgeDate) {
            showError('playerDob', 'You must be at least 10 years old to register');
            return;
        }

        // Show loading state
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Registering...';
        }

        // Get additional fields
        const address = document.getElementById('playerAddress')?.value.trim() || null;
        const city = document.getElementById('playerCity')?.value.trim() || null;
        const state = document.getElementById('playerState')?.value.trim() || null;
        const country = document.getElementById('playerCountry')?.value.trim() || null;
        const pincode = document.getElementById('playerPincode')?.value.trim() || null;
        const bio = document.getElementById('playerBio')?.value.trim() || null;
        const height = document.getElementById('playerHeight')?.value ?
            parseInt(document.getElementById('playerHeight').value) : null;
        const weight = document.getElementById('playerWeight')?.value ?
            parseFloat(document.getElementById('playerWeight').value) : null;

        // Get event ID from form dataset
        const eventId = form.dataset.eventId ? parseInt(form.dataset.eventId) : null;

        // Prepare request data with all fields
        const requestData = {
            firstName,
            lastName,
            email,
            phone,
            dateOfBirth: dob,
            gender: genderValue,
            password,
            address,
            city,
            state,
            country,
            pincode,
            bio,
            height_cm: height,
            weight_kg: weight,
            eventId: eventId
        };

        // Collect sport ratings
        const sportRatingInputs = document.querySelectorAll('.sport-rating-input');
        const sportRatings = [];

        sportRatingInputs.forEach(input => {
            const sportId = parseInt(input.dataset.sportId);
            const rating = parseInt(input.value) || 0; // Default to 0 if empty

            // Validate rating
            if (rating < 0 || rating > 10) {
                throw new Error(`Invalid rating for ${input.dataset.sportName}. Must be between 0 and 10.`);
            }

            sportRatings.push({
                sport_id: sportId,
                rating: rating
            });
        });

        // Add sport ratings to request data
        if (sportRatings.length > 0) {
            requestData.sportRatings = sportRatings;
        }


        console.log('Sending registration data:', JSON.stringify(requestData, null, 2));

        // Make the API request
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

        const response = await fetch('/register/player', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        // Handle response
        let result;
        try {
            result = await response.json();
            console.log('Registration response:', result); // Debug log
        } catch (jsonError) {
            const text = await response.text();
            console.error('Invalid server response:', text); // Debug log
            throw new Error(`Invalid server response: ${text}`);
        }

        console.log('Response status:', response.status, response.ok); // Debug log

        if (!response.ok) {
            const errorMessage = result.detail || result.message ||
                (result.error || 'Registration failed');
            throw new Error(errorMessage);
        }

        // Show success message
        showModal('Registration Successful!',
            `Thank you ${firstName}! Your registration was successful. You can now log in with your credentials.`);

        // Close the modal and reset the form
        closeModal('playerRegistrationModal');
        form.reset();

    } catch (error) {
        console.error('Registration error:', error);
        const errorMessage = error.message || 'An error occurred during registration. Please try again.';
        showModal('Registration Failed', errorMessage);
    } finally {
        // Reset button state
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = 'Register';
        }
    }
}

function calculateAge(dateOfBirth) {
    if (!dateOfBirth) return null;
    const today = new Date();
    const birthDate = new Date(dateOfBirth);
    let age = today.getFullYear() - birthDate.getFullYear();
    const monthDiff = today.getMonth() - birthDate.getMonth();

    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
        age--;
    }

    return age;
}

function validatePlayerData(data) {
    const errors = [];

    if (!data.name || data.name.trim().length < 2) {
        errors.push('Please enter a valid name (at least 2 characters)');
    }

    if (!data.email || !isValidEmail(data.email)) {
        errors.push('Please enter a valid email address');
    }

    if (!data.phone || data.phone.length < 10) {
        errors.push('Please enter a valid phone number');
    }

    if (!data.age || data.age < 16 || data.age > 60) {
        errors.push('Age must be between 16 and 60');
    }

    if (!data.gender) {
        errors.push('Please select your gender');
    }

    // Skill rating validation has been removed

    if (errors.length > 0) {
        showModal('Registration Error', errors.join('<br>'));
        return false;
    }

    return true;
}

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}



// Handle click outside modal to close
document.addEventListener('click', function (event) {
    const modals = document.querySelectorAll('.modal-overlay');
    modals.forEach(modal => {
        if (event.target === modal) {
            // Log the click outside modal close
            adminLogActivity('Modal Closed by Click Outside', `Modal: ${modal.id || 'Unknown'}`, 'player');
            modal.style.display = 'none';
            modal.classList.remove('active');
            document.body.style.overflow = '';

            // Also clear form when clicking outside
            const form = document.getElementById('playerRegistrationForm');
            if (form) {
                form.reset();
            }

            // Clear success section if visible
            const successSection = document.getElementById('successSection');
            if (successSection) {
                successSection.style.display = 'none';
            }
        }
    });
});

// Card hover effects and URL parameter handling
// DOMContentLoaded consolidated above

// Live auction pulse effect (for any remaining live indicators)
let pulseIntervals = [];
function addLivePulseEffect() {
    // Clear existing intervals
    pulseIntervals.forEach(interval => clearInterval(interval));
    pulseIntervals = [];

    const liveIndicators = document.querySelectorAll('.live-indicator');
    liveIndicators.forEach(indicator => {
        const interval = setInterval(() => {
            indicator.style.opacity = indicator.style.opacity === '0.7' ? '1' : '0.7';
        }, 1000);
        pulseIntervals.push(interval);
    });
}

// Event Sports Configuration - Set by Admin for each event
const eventSportsData = {
    1: { // Pro League Combine 2025
        sports: [
            { id: 'football', name: 'Football', icon: '⚽', description: 'Rate your passing, shooting, and defensive skills' },
            { id: 'basketball', name: 'Basketball', icon: '🏀', description: 'Rate your shooting, passing, and defensive skills' },
            { id: 'tennis', name: 'Tennis', icon: '🎾', description: 'Rate your serve, forehand, and backhand skills' },
            { id: 'cricket', name: 'Cricket', icon: '🏏', description: 'Rate your batting, bowling, and fielding skills' },
            { id: 'hockey', name: 'Hockey', icon: '🏒', description: 'Rate your stick handling and shooting skills' }
        ]
    },
    2: { // Championship Auction 2025
        sports: [
            { id: 'basketball', name: 'Basketball', icon: '🏀', description: 'Rate your shooting, passing, and defensive skills' },
            { id: 'football', name: 'Football', icon: '⚽', description: 'Rate your passing, shooting, and defensive skills' },
            { id: 'volleyball', name: 'Volleyball', icon: '🏐', description: 'Rate your serving, spiking, and blocking skills' },
            { id: 'badminton', name: 'Badminton', icon: '🏸', description: 'Rate your smash, drop shot, and net play skills' },
            { id: 'tennis', name: 'Tennis', icon: '🎾', description: 'Rate your serve, forehand, and backhand skills' }
        ]
    }
    // Add more events as needed with admin-configured sports
};

// Initialize pulse effect
// DOMContentLoaded consolidated above

function getSportName(sportId) {
    const sports = {
        'cricket': 'Cricket',
        'football': 'Football',
        'basketball': 'Basketball',
        'tennis': 'Tennis',
        'hockey': 'Hockey',
        'badminton': 'Badminton',
        'volleyball': 'Volleyball',
        'baseball': 'Baseball',
        'swimming': 'Swimming',
        'athletics': 'Athletics'
    };
    return sports[sportId] || sportId;
}

function registerForEvent(event, eventId) {
    try {
        // Prevent default form submission if event is provided
        if (event && typeof event.preventDefault === 'function') {
            event.preventDefault();
        }

        // If eventId is not provided, try to get it from the event target's data attribute
        if (!eventId && event && event.target) {
            eventId = event.target.getAttribute('data-event-id') || 1;
        }

        // Default to event ID 1 if not provided
        eventId = eventId || 1;

        // Open registration modal for the specific event
        openRegistrationModal(eventId);
    } catch (error) {
        console.error('Error in registerForEvent:', error);
    }
}

// Validate session on page load
function validateSessionOnLoad() {
    // Only check if we think we're logged in
    if (sessionStorage.getItem('isAuthenticated') === 'true') {
        fetch('/api/session/validate')
            .then(response => {
                if (!response.ok) {
                    // Session invalid/expired
                    console.warn('Session expired or invalid');
                    // Clear local state but don't redirect immediately to avoid loops if on public pages
                    sessionStorage.removeItem('isAuthenticated');
                    sessionStorage.removeItem('user_type');
                    sessionStorage.removeItem('username');
                    sessionStorage.removeItem('user_id');
                    sessionStorage.removeItem('email');

                    // If on a dashboard page, redirect to home
                    if (window.location.pathname.includes('dashboard')) {
                        window.location.href = '/index.html';
                    }
                } else {
                    console.log('Session validated successfully');
                }
            })
            .catch(err => {
                console.error('Error validating session:', err);
            });
    }
}

// Run validation on load
document.addEventListener('DOMContentLoaded', validateSessionOnLoad);

// Toggle password visibility
window.togglePasswordVisibility = function(inputId, iconElement) {
    const input = document.getElementById(inputId);
    if (input.type === 'password') {
        input.type = 'text';
        iconElement.classList.remove('fa-eye');
        iconElement.classList.add('fa-eye-slash');
    } else {
        input.type = 'password';
        iconElement.classList.remove('fa-eye-slash');
        iconElement.classList.add('fa-eye');
    }
};
