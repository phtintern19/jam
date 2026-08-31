// --- SIDEBAR MANAGEMENT ---
function toggleSidebar() {
    const sidebar = document.getElementById('adminSidebar');
    if (sidebar) {
        sidebar.classList.toggle('sidebar-open');
    }
}

// --- THEME MANAGEMENT ---
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

document.addEventListener('DOMContentLoaded', () => {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
});
// ------------------------

// Events data will be fetched from API
let eventsData = [];

// Pagination state for player registrations
let playerCurrentPage = 1;
let playerPageSize = 25;
let playerTotalCount = 0;

// Pagination state for team owner registrations
let teamOwnerCurrentPage = 1;
let teamOwnerPageSize = 25;
let teamOwnerTotalCount = 0;

// Current view event ID
let currentViewEventId = null;

// Sorting state for player registrations
let playerSortByEventId = false;
let playerEventIdSortAscending = true;

// --- CENTRALIZED API CONFIGURATION & DIAGNOSTICS ---
const API_BASE_URL = window.API_BASE_URL || '';

async function apiFetch(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
    try {
        const response = await fetch(url, options);
        return response;
    } catch (error) {
        if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
            console.error(`[API Network/CORS Error] Failed to reach ${url}. 
            This usually means:
            1. The backend server is down or unreachable.
            2. You are loading the HTML via file:/// instead of a web server.
            3. A CORS policy blocked the request (e.g. credentials mismatch).
            4. Mixed content was blocked (HTTPS to HTTP).`, error);
        } else {
            console.error(`[API Error] Error calling ${url}:`, error);
        }
        throw error;
    }
}

// Players will be fetched from API
let samplePlayers = [];


async function loadDashboardStats() {
    try {
        const response = await apiFetch('/api/dashboard/admin/stats');
        if (response.ok) {
            const stats = await response.json();
            // Update the reports section cards if they exist
            const elRevenue = document.getElementById('reportTotalRevenue');
            const elTeams = document.getElementById('reportTotalTeams');
            const elPlayers = document.getElementById('reportTotalPlayers');
            const elSold = document.getElementById('reportSoldPlayers');
            if (elRevenue) elRevenue.textContent = `$${stats.auction_revenue || 0}M`;
            if (elTeams) elTeams.textContent = stats.total_teams || 0;
            if (elPlayers) elPlayers.textContent = stats.total_players || 0;
            if (elSold) elSold.textContent = stats.purchased_players || 0;
        } else {
            console.error(`[API HTTP Error] loadDashboardStats failed with status: ${response.status}`);
        }
    } catch (error) {
        console.error('Error loading dashboard stats:', error);
    }
}

// Keep existing loadSystemStats signature so we don't break function calls elsewhere,
// but point it to the real dashboard stats.
async function loadSystemStats() {
    await loadDashboardStats();
}

// Load events into the grid
async function loadEvents() {
    const eventsGrid = document.getElementById('eventsGrid');
    eventsGrid.innerHTML = '<div style="color: #94a3b8; text-align: center; grid-column: 1/-1;">Loading events...</div>';

    try {
        const response = await apiFetch('/api/events/?_t=' + new Date().getTime());
        if (!response.ok) {
            console.error(`[API HTTP Error] loadEvents failed with status: ${response.status}`);
            throw new Error(`Failed to fetch events (Status: ${response.status})`);
        }
        
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Non-JSON response from /events/:', text);
            throw new Error('Server returned non-JSON response. Please check if the backend is running correctly.');
        }
        
        eventsData = await response.json();

        // Update summary cards
        const totalEvents = eventsData.length;
        const activeEvents = eventsData.filter(e => e.status && e.status.toUpperCase() === 'ACTIVE').length;
        const upcomingEvents = eventsData.filter(e => e.status && e.status.toUpperCase() === 'UPCOMING').length;
        const completedEvents = eventsData.filter(e => e.status && e.status.toUpperCase() === 'COMPLETED').length;

        const summaryTotalEvents = document.getElementById('summaryTotalEvents');
        const summaryActiveEvents = document.getElementById('summaryActiveEvents');
        const summaryUpcomingEvents = document.getElementById('summaryUpcomingEvents');
        const summaryCompletedEvents = document.getElementById('summaryCompletedEvents');

        if (summaryTotalEvents) summaryTotalEvents.textContent = totalEvents;
        if (summaryActiveEvents) summaryActiveEvents.textContent = activeEvents;
        if (summaryUpcomingEvents) summaryUpcomingEvents.textContent = upcomingEvents;
        if (summaryCompletedEvents) summaryCompletedEvents.textContent = completedEvents;

        eventsGrid.innerHTML = '';
        if (eventsData.length === 0) {
            eventsGrid.innerHTML = '<div style="color: #94a3b8; text-align: center; grid-column: 1/-1;">No events found. Create one to get started.</div>';
            return;
        }

        eventsData.forEach(event => {
            const eventCard = createEventCard(event);
            eventsGrid.appendChild(eventCard);
        });

        // Populate event filter dropdown for player registrations
        populateEventFilterDropdown();
    } catch (error) {
        console.error('Error loading events:', error);
        if (eventsGrid) {
            eventsGrid.innerHTML = '<div style="color: #ef4444; text-align: center; grid-column: 1/-1;">Error loading events. Please try again later.</div>';
        }
    }
}

// Create event card HTML
function createEventCard(event) {
    const card = document.createElement('div');
    card.className = 'event-card';

    // Format date
    const eventDate = new Date(event.start_date).toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });

    // Format sports
    const sportsList = event.sports ? event.sports.map(s => s.name) : [];

    // Format budget
    const budget = event.budget ? parseFloat(event.budget) : 0;

    // Format base prices
    let basePrices = { diamond: 0, platinum: 0, gold: 0, silver: 0 };
    if (event.base_prices) {
        try {
            // Parse if it's a JSON string
            if (typeof event.base_prices === 'string') {
                basePrices = JSON.parse(event.base_prices);
            } else {
                basePrices = event.base_prices;
            }
        } catch (e) {
            console.error('Error parsing base_prices:', e);
            basePrices = { diamond: 0, platinum: 0, gold: 0, silver: 0 };
        }
    }

    card.innerHTML = `
        <div class="event-card-header" style="position: relative; height: 120px; background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%); border-radius: 1rem 1rem 0 0; padding: 1rem;">
            <div class="sport-icon" style="position: absolute; top: 1rem; left: 1rem; width: 40px; height: 40px; background: rgba(255,255,255,0.2); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 1.25rem;">
                <i class="fas fa-trophy"></i>
            </div>
            <div class="event-status status-${(event.status || 'UPCOMING').toLowerCase()}" style="position: absolute; top: 1rem; right: 1rem; background: rgba(0,0,0,0.5); color: white; padding: 0.25rem 0.75rem; border-radius: 1rem; font-size: 0.75rem; text-transform: uppercase; font-weight: 600; border: 1px solid rgba(255,255,255,0.2);">
                ${event.status || 'UPCOMING'}
            </div>
            <h3 style="position: absolute; bottom: 1rem; left: 1rem; margin: 0; color: white; font-size: 1.25rem; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">${event.title}</h3>
        </div>
        
        <div class="event-card-body" style="padding: 1.5rem;">
            <div class="event-meta" style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1.5rem;">
                <div class="meta-item" style="display: flex; align-items: flex-start; gap: 0.5rem; color: #64748b; font-size: 0.875rem;">
                    <i class="far fa-calendar" style="margin-top: 0.25rem;"></i>
                    <span><strong>Date</strong><br>${eventDate}</span>
                </div>
                <div class="meta-item" style="display: flex; align-items: flex-start; gap: 0.5rem; color: #64748b; font-size: 0.875rem;">
                    <i class="fas fa-map-marker-alt" style="margin-top: 0.25rem;"></i>
                    <span><strong>Venue</strong><br>${event.location || 'N/A'}</span>
                </div>
            </div>

            <div class="event-stats" style="display: flex; justify-content: space-between; align-items: center; padding-top: 1rem; border-top: 1px solid var(--border-color, #e2e8f0); margin-bottom: 1.5rem;">
                <div class="stat" style="text-align: left;">
                    <div style="font-size: 0.75rem; color: #64748b; text-transform: uppercase; font-weight: 600;">Registered Teams</div>
                    <div style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary, #0f172a);">${event.registered_teams_count || 0}</div>
                </div>
                <div class="stat" style="text-align: right;">
                    <div style="font-size: 0.75rem; color: #64748b; text-transform: uppercase; font-weight: 600;">Auction Status</div>
                    <div style="font-size: 0.875rem; font-weight: 600; color: #10b981;">Ready</div>
                </div>
            </div>

            <div class="event-actions" style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
                <button class="btn btn-outline-indigo" style="padding: 0.5rem; border-radius: 0.5rem; border: 1px solid #cbd5e1; background: transparent; cursor: pointer; transition: all 0.2s;" onclick="editEvent('${event.event_id}')">
                    <i class="fas fa-edit"></i> Edit
                </button>
                <button class="btn btn-outline-success" style="padding: 0.5rem; border-radius: 0.5rem; border: 1px solid #cbd5e1; background: transparent; cursor: pointer; transition: all 0.2s;" onclick="openAuctionPrepModal('${event.event_id}')">
                    <i class="fas fa-gavel"></i> Start Auction
                </button>
                <button class="btn btn-outline-secondary" style="padding: 0.5rem; border-radius: 0.5rem; border: 1px solid #cbd5e1; background: transparent; cursor: pointer; transition: all 0.2s;" onclick="viewEventTeams('${event.event_id}', '${event.title.replace(/'/g, "\\'")}')">
                    <i class="fas fa-users"></i> Teams
                </button>
                <button class="btn btn-outline-danger" style="padding: 0.5rem; border-radius: 0.5rem; border: 1px solid #cbd5e1; background: transparent; cursor: pointer; transition: all 0.2s; color: #ef4444;" onclick="deleteEvent('${event.event_id}')">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>
        </div>
    `;
    // Add glassmorphism classes to the main card
    card.classList.add('glass-card');
    card.style.padding = '0';
    card.style.overflow = 'hidden';
    card.style.display = 'flex';
    card.style.flexDirection = 'column';
    return card;
}

// Open create event modal
function openCreateEventModal() {
    // Log the create event action
    if (typeof logActivity === 'function') {
        logActivity('Create Event Modal Opened', 'Admin started creating a new event', 'admin');
    }

    // Clear the form
    document.getElementById('editEventForm').reset();
    document.getElementById('editEventName').value = '';
    document.getElementById('editEventDate').value = '';
    document.getElementById('editEventLocation').value = '';
    document.getElementById('editMaxBudget').value = '';
    document.getElementById('editPriceDiamond').value = '';
    document.getElementById('editPricePlatinum').value = '';
    document.getElementById('editPriceGold').value = '';
    document.getElementById('editPriceSilver').value = '';

    // Update modal title
    document.querySelector('#editEventModal .modal-header h2').textContent = 'Create New Event';
    document.querySelector('#editEventModal .modal-subtitle').textContent = 'Fill in the details below to create a new auction event.';

    // Clear sport id selection
    let sportIdSelect = document.getElementById('editSportId');
    if (sportIdSelect) sportIdSelect.value = '';

    // Default bid time to 20 seconds
    const defaultEditBid = document.getElementById('editBidTime');
    if (defaultEditBid) defaultEditBid.value = 20;

    // Show modal
    document.getElementById('editEventModal').classList.add('active');

    // Store that we're creating, not editing
    document.getElementById('editEventForm').dataset.mode = 'create';
}

// Edit event
function editEvent(eventId) {
    // Note: eventId is now an integer from the DB, but passed as string in HTML attributes
    const event = eventsData.find(e => e.event_id == eventId);
    if (!event) return;

    // Store current event ID for action buttons
    currentEventId = eventId;

    // Log the edit event action
    if (typeof logActivity === 'function') {
        logActivity('Edit Event Modal Opened', `Event ID: ${eventId}, Event: ${event.title}`, 'admin');
    }

    // Update modal title
    document.querySelector('#editEventModal .modal-header h2').textContent = 'Edit Auction Event';
    document.querySelector('#editEventModal .modal-subtitle').textContent = 'Fill in the details below to update this auction event.';

    // Populate form
    document.getElementById('editEventName').value = event.title;

    // Ensure date string is treated as UTC
    let dateStr = event.start_date;
    if (dateStr && !dateStr.endsWith('Z') && !dateStr.includes('+')) {
        dateStr += 'Z';
    }
    const startDate = new Date(dateStr);

    const year = startDate.getFullYear();
    const month = String(startDate.getMonth() + 1).padStart(2, '0');
    const day = String(startDate.getDate()).padStart(2, '0');
    document.getElementById('editEventDate').value = `${year}-${month}-${day}`;

    let hours = startDate.getHours();
    const minutes = String(startDate.getMinutes()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';

    hours = hours % 12;
    hours = hours ? hours : 12; // the hour '0' should be '12'

    document.getElementById('editEventHour').value = hours;
    document.getElementById('editEventMinute').value = minutes;
    document.getElementById('editEventAmPm').value = ampm;
    document.getElementById('editEventLocation').value = event.location;
    document.getElementById('editMaxBudget').value = event.budget;

    const basePrices = event.base_prices || {};
    document.getElementById('editPriceDiamond').value = basePrices.diamond || '';
    document.getElementById('editPricePlatinum').value = basePrices.platinum || '';
    document.getElementById('editPriceGold').value = basePrices.gold || '';
    document.getElementById('editPriceSilver').value = basePrices.silver || '';

    // Select the correct sport in the dropdown
    let sportIdSelect = document.getElementById('editSportId');
    if (sportIdSelect) {
        // If event has sports attached via the old event_sports table, grab the first one.
        // For new events, event.sport_id would be ideal but we use event.sports for backward compatibility.
        if (event.sports && event.sports.length > 0) {
            sportIdSelect.value = event.sports[0].sport_id;
        } else {
            sportIdSelect.value = '';
        }
    }

    // Populate bid time selection
    const bidTime = event.bid_time_limit || 20;
    const bidInput = document.getElementById('editBidTime');
    if (bidInput) bidInput.value = bidTime;

    // Populate new fields
    document.getElementById('editRegistrationFee').value = event.registration_fee || 0;
    document.getElementById('editMaxPlayers').value = event.max_players || '';
    document.getElementById('editMaxTeams').value = event.max_teams || '';
    document.getElementById('editExtraInfo').value = event.extra_info || '';

    // Show modal
    document.getElementById('editEventModal').classList.add('active');

    // Store event ID for saving
    document.getElementById('editEventForm').dataset.eventId = eventId;
    document.getElementById('editEventForm').dataset.mode = 'edit';
}



// Convert date string to input format
function convertDateToInput(dateString) {
    // Parse "Tuesday, October 15, 2024" format
    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Close edit event modal
function closeEditEventModal() {
    if (typeof logActivity === 'function') {
        logActivity('Edit Event Modal Closed', 'User cancelled event creation/editing', 'admin');
    }
    document.getElementById('editEventModal').classList.remove('active');
}

// Save event
async function saveEvent() {
    const form = document.getElementById('editEventForm');
    const mode = form.dataset.mode;
    const eventId = form.dataset.eventId;

    // Get selected sports from hidden inputs
    const selectedSports = [];
    document.querySelectorAll('#editSportsCheckboxes input[type="hidden"]').forEach(input => {
        selectedSports.push(input.value);
    });

    // Read selected bid time for this event (per-bid seconds)
    const bidTimeInput = document.getElementById('editBidTime');
    const selectedBidTime = bidTimeInput ? parseInt(bidTimeInput.value) : 20;

    // Validate bid time range (10-60 seconds)
    if (selectedBidTime < 10 || selectedBidTime > 60) {
        showModal('Invalid Time', 'Bid time must be between 10 and 60 seconds.');
        return;
    }

    // Construct date with time
    let hours = parseInt(document.getElementById('editEventHour').value);
    const minutes = String(document.getElementById('editEventMinute').value).padStart(2, '0');
    const ampm = document.getElementById('editEventAmPm').value;

    // Validate inputs
    if (isNaN(hours) || hours < 1 || hours > 12) {
        showModal('Invalid Time', 'Hour must be between 1 and 12');
        return;
    }

    // Convert to 24-hour format
    if (ampm === 'PM' && hours < 12) hours += 12;
    if (ampm === 'AM' && hours === 12) hours = 0;

    const timeString = `${String(hours).padStart(2, '0')}:${minutes}`;

    // Create event object
    const eventData = {
        title: document.getElementById('editEventName').value,
        start_date: new Date(`${document.getElementById('editEventDate').value}T${timeString}`).toISOString(),
        end_date: new Date(`${document.getElementById('editEventDate').value}T${timeString}`).toISOString(), // Using same date for now
        location: document.getElementById('editEventLocation').value,
        sport_id: parseInt(document.getElementById('editSportId').value), // Send actual sport ID
        budget: parseFloat(document.getElementById('editMaxBudget').value),
        base_prices: {
            diamond: parseFloat(document.getElementById('editPriceDiamond').value),
            platinum: parseFloat(document.getElementById('editPricePlatinum').value),
            gold: parseFloat(document.getElementById('editPriceGold').value),
            silver: parseFloat(document.getElementById('editPriceSilver').value)
        },
        bid_time_limit: selectedBidTime,
        status: 'upcoming',
        registration_fee: parseFloat(document.getElementById('editRegistrationFee').value) || 0,
        max_players: document.getElementById('editMaxPlayers').value ? parseInt(document.getElementById('editMaxPlayers').value) : null,
        max_teams: document.getElementById('editMaxTeams').value ? parseInt(document.getElementById('editMaxTeams').value) : null,
        extra_info: document.getElementById('editExtraInfo').value || null
    };
    // (Backward compatibility handled by backend API which will map sport_id into the event_sports join table if needed)
    try {
        let url = '/events/';
        let method = 'POST';

        if (mode === 'edit') {
            url = `/events/${eventId}`;
            method = 'PUT';
        }

        const response = await apiFetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(eventData)
        });

        if (!response.ok) {
            let errorMessage = 'Failed to save event';
            try {
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const errorData = await response.json();
                    errorMessage = errorData.detail || errorData.message || errorMessage;
                } else {
                    const errorText = await response.text();
                    console.error('Non-JSON error response:', errorText);
                    errorMessage = `Server error (${response.status}): ${response.statusText}`;
                }
            } catch (parseError) {
                console.error('Error parsing error response:', parseError);
                errorMessage = `Server error (${response.status}): ${response.statusText}`;
            }
            throw new Error(errorMessage);
        }

        // Close modal and reload events
        closeEditEventModal();
        loadEvents();

        // Log the save event action
        if (typeof logActivity === 'function') {
            logActivity(mode === 'edit' ? 'Event Updated' : 'Event Created', `Event: ${eventData.title}`, 'admin');
        }

        showModal('Success', `Event ${mode === 'edit' ? 'updated' : 'created'} successfully!`);

    } catch (error) {
        console.error('Error saving event:', error);
        showModal('Error', error.message);
    }
}

// View event registrations
function viewEventRegistrations(eventId, eventTitle) {
    currentViewEventId = eventId;

    // Update section headers
    const playerHeader = document.querySelector('#registrationsSection .section-header h3');
    if (playerHeader) playerHeader.innerHTML = `<i class="fas fa-user-plus"></i> Player Registrations - ${eventTitle}`;

    const ownerHeader = document.querySelector('#teamOwnerRegistrationsSection .section-header h3');
    if (ownerHeader) ownerHeader.innerHTML = `<i class="fas fa-users-cog"></i> Team Owner Registrations - ${eventTitle}`;

    // Scroll to registrations
    document.getElementById('registrationsSection').scrollIntoView({ behavior: 'smooth' });

    // Reload data
    playerCurrentPage = 1;
    teamOwnerCurrentPage = 1;
    loadTeamOwnerRegistrations();
}

let teamsModalElement = null;

async function viewEventTeams(eventId, eventTitle) {
    if (document.getElementById('teamsLoadingModal')) return; // Prevent duplicate requests
    
    // Create loading modal
    teamsModalElement = document.createElement('div');
    teamsModalElement.id = 'teamsLoadingModal';
    teamsModalElement.style.cssText = 'position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 9999;';
    
    // Make sure we use a close button with a clear label as requested
    teamsModalElement.innerHTML = 
        '<div class="glass-card" style="background: var(--bg-card, #ffffff); padding: 2rem; border-radius: 1rem; min-width: 400px; max-width: 90vw; max-height: 80vh; overflow-y: auto; position: relative;">' +
            '<div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border-color, #e2e8f0); padding-bottom: 1rem;">' +
                '<div>' +
                    '<h3 style="margin: 0; font-size: 1.25rem; font-weight: 700;">REGISTERED TEAMS</h3>' +
                    '<div style="color: #64748b; font-size: 0.875rem; margin-top: 0.25rem;">' + eventTitle + '</div>' +
                '</div>' +
                '<button onclick="closeTeamsModal()" style="background: var(--bg-card, #ffffff); border: 1px solid var(--border-color, #e2e8f0); border-radius: 0.25rem; padding: 0.25rem 0.75rem; cursor: pointer; color: var(--text-primary, #0f172a); font-weight: 600;">&times; Close</button>' +
            '</div>' +
            '<div id="teamsModalContent" style="text-align: center; padding: 2rem;">' +
                '<i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: #3b82f6; margin-bottom: 1rem;"></i>' +
                '<div>Loading registered teams...</div>' +
            '</div>' +
        '</div>';
    document.body.appendChild(teamsModalElement);
    
    try {
        const response = await apiFetch('/api/events/' + eventId + '/teams');
        
        let data = null;
        try {
            data = await response.json();
        } catch (e) {
            // Not JSON
        }

        if (!response.ok) {
            if (response.status === 401) throw new Error("Your session has expired. Please log in again.");
            if (response.status === 403) throw new Error("You do not have permission to view registered teams.");
            if (response.status === 404) throw new Error("Event not found.");
            
            const errorMsg = data && data.message ? data.message : "Failed to load teams. Server error " + response.status;
            throw new Error(errorMsg);
        }
        
        const contentDiv = document.getElementById('teamsModalContent');
        if (!contentDiv) return;
        
        if (!data || !data.teams || data.teams.length === 0) {
            contentDiv.innerHTML = 
                '<div style="text-align: center; padding: 2rem;">' +
                    '<i class="fas fa-users-slash" style="font-size: 3rem; color: #94a3b8; margin-bottom: 1rem;"></i>' +
                    '<h4 style="margin: 0 0 0.5rem 0;">No teams registered</h4>' +
                    '<p style="color: #64748b; margin: 0;">There are currently no teams registered for this event.</p>' +
                '</div>';
            return;
        }
        
        let html = '<div style="display: flex; flex-direction: column; gap: 1rem; text-align: left;">';
        data.teams.forEach(team => {
            html += 
                '<div style="border: 1px solid var(--border-color, #e2e8f0); border-radius: 0.5rem; padding: 1rem;">' +
                    '<div style="font-weight: 700; font-size: 1.125rem; color: var(--text-primary, #0f172a); margin-bottom: 0.25rem;">' + team.team_name + '</div>' +
                    '<div style="color: #64748b; font-size: 0.875rem;">' +
                        '<div><i class="fas fa-user-tie" style="width: 16px;"></i> Owner: ' + team.owner_name + '</div>' +
                        '<div><i class="fas fa-users" style="width: 16px;"></i> Players: ' + team.players_count + '</div>' +
                    '</div>' +
                '</div>';
        });
        html += '</div>';
        
        contentDiv.innerHTML = html;
        
    } catch (error) {
        const contentDiv = document.getElementById('teamsModalContent');
        if (contentDiv) {
            contentDiv.innerHTML = 
                '<div style="text-align: center; padding: 2rem; color: #ef4444;">' +
                    '<i class="fas fa-exclamation-circle" style="font-size: 3rem; margin-bottom: 1rem;"></i>' +
                    '<h4 style="margin: 0 0 0.5rem 0;">Error</h4>' +
                    '<p style="margin: 0;">' + error.message + '</p>' +
                '</div>';
        }
        console.error("Error loading teams:", error);
    }
}

function closeTeamsModal() {
    if (teamsModalElement) {
        teamsModalElement.remove();
        teamsModalElement = null;
    }
}


// Delete event
async function deleteEvent(eventId) {
    if (confirm('Are you sure you want to delete this event? This action cannot be undone.')) {
        try {
            const response = await apiFetch(`/api/events/${eventId}`, {
                method: 'DELETE'
            });

            let data = {};
            try {
                data = await response.json();
            } catch (e) {
                // If response is not JSON
            }

            if (!response.ok || data.success === false) {
                const errorMsg = data.message || (response.status === 404 ? 'Event not found.' : 'Failed to delete event.');
                throw new Error(errorMsg);
            }

            alert(data.message || 'Event deleted successfully!');

            if (typeof logActivity === 'function') {
                logActivity('Event Deleted', `ID: ${eventId}`, 'admin');
            }

            loadEvents();
        } catch (error) {
            console.error('Error deleting event:', error);
            showModal('Error', error.message || 'Failed to delete event. Please try again.');
        }
    }
}

// View players
async function viewPlayers(eventId) {
    const event = eventsData.find(e => e.id === eventId) || window.eventsData?.[eventId];
    if (!event) return;

    // Log the view players action
    if (typeof logActivity === 'function') {
        logActivity('View Players', `Event ID: ${eventId}, Event: ${event.title || event.name}`, 'admin');
    }

    // Update modal title
    document.getElementById('playersModalTitle').textContent = `Registered Players for ${event.title || event.name}`;
    
    // Show modal immediately to indicate loading
    document.getElementById('viewPlayersModal').classList.add('active');

    // Load players
    const playersGrid = document.getElementById('playersGrid');
    playersGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #64748b;">Loading players...</div>';

    try {
        const response = await apiFetch(`/api/events/${eventId}/players`);
        if (!response.ok) throw new Error('Failed to fetch players');
        
        const players = await response.json();
        playersGrid.innerHTML = '';
        
        if (players.length === 0) {
            playersGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #64748b;">No players registered for this event yet.</div>';
            return;
        }

        players.forEach(player => {
            const playerCard = createPlayerCard(player);
            playersGrid.appendChild(playerCard);
        });
    } catch (error) {
        console.error('Error fetching players:', error);
        playersGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #ef4444;">Error loading players. Please try again later.</div>';
    }
}

// Create player card
function createPlayerCard(player) {
    const card = document.createElement('div');
    card.className = 'player-card';

    const categoryClass = `badge-${player.category}`;
    const categoryIcon = getCategoryIcon(player.category);

    card.innerHTML = `
        <img src="${player.image}" alt="${player.name}" class="player-image">
        <div class="player-badge ${categoryClass}">
            <i class="${categoryIcon}"></i>
            ${player.category.charAt(0).toUpperCase() + player.category.slice(1)}
        </div>
        <div class="player-info">
            <h3 class="player-name">${player.name}</h3>
            <div class="player-stats">
                <div class="stat-item">
                    <div class="stat-icon"><i class="fas fa-star"></i></div>
                    <div class="stat-value">${player.rating}/10</div>
                    <div class="stat-label">Rating</div>
                </div>
                <div class="stat-item">
                    <div class="stat-icon"><i class="fas fa-trophy"></i></div>
                    <div class="stat-value">${player.wins}</div>
                    <div class="stat-label">Wins</div>
                </div>
                <div class="stat-item">
                    <div class="stat-icon"><i class="fas fa-times"></i></div>
                    <div class="stat-value">${player.losses}</div>
                    <div class="stat-label">Losses</div>
                </div>
            </div>
            <div class="player-price">
                <i class="fas fa-coins"></i>
                <span class="price-label-small">Base Price:</span>
                <span class="price-amount-large">$${player.basePrice.toLocaleString()}</span>
            </div>
            <button class="view-profile-btn">
                <i class="fas fa-user"></i>
                View Profile
            </button>
        </div>
    `;
    return card;
}

// Get category icon
function getCategoryIcon(category) {
    const icons = {
        diamond: 'fas fa-gem',
        platinum: 'fas fa-certificate',
        gold: 'fas fa-medal',
        silver: 'fas fa-award'
    };
    return icons[category] || 'fas fa-trophy';
}

// Close players modal
function closePlayersModal() {
    if (typeof logActivity === 'function') {
        logActivity('Players Modal Closed', 'Admin closed player viewing modal', 'admin');
    }
    document.getElementById('viewPlayersModal').classList.remove('active');
}

// Generate live link
function generateLiveLink(eventId) {
    const event = eventsData.find(e => e.id === eventId);
    if (!event) return;

    const liveLink = `${window.location.origin}/templates/event-details.html?id=${eventId}`;
    alert(`Live Link Generated:\n${liveLink}`);
    if (typeof logActivity === 'function') {
        logActivity('Live Link Generated', `Event ID: ${eventId}`, 'admin');
    }
}

// Copy link
function copyLink(eventId) {
    const liveLink = `${window.location.origin}/templates/event-details.html?id=${eventId}`;

    // Create a temporary input element
    const tempInput = document.createElement('input');
    tempInput.value = liveLink;
    document.body.appendChild(tempInput);
    tempInput.select();
    document.execCommand('copy');
    document.body.removeChild(tempInput);

    alert('Link copied to clipboard!');
    if (typeof logActivity === 'function') {
        logActivity('Live Link Copied', `Event ID: ${eventId}`, 'admin');
    }
}

// Logout function
async function logout() {
    if (confirm('Are you sure you want to logout?')) {
        try {
            await apiFetch('/api/logout', { method: 'POST' });
        } catch (error) {
            console.error('Error logging out:', error);
        }
        
        // Clear all session storage
        sessionStorage.clear();
        
        // Clear all local storage
        localStorage.removeItem('user');
        localStorage.removeItem('session_token');
        localStorage.removeItem('userType');
        localStorage.removeItem('username');
        localStorage.removeItem('teamName');

        // Redirect to home page
        window.location.replace('/');
    }
}

// Show modal function for admin dashboard
function showModal(title, message) {
    // Create modal if it doesn't exist
    let modal = document.querySelector('.modal-overlay');
    if (!modal) {
        modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.style.display = 'none';
        modal.style.position = 'fixed';
        modal.style.top = '0';
        modal.style.left = '0';
        modal.style.width = '100%';
        modal.style.height = '100%';
        modal.style.backgroundColor = 'rgba(0, 0, 0, 0.7)';
        modal.style.display = 'flex';
        modal.style.justifyContent = 'center';
        modal.style.alignItems = 'center';
        modal.style.zIndex = '1000';

        // Create modal content
        const modalContent = document.createElement('div');
        modalContent.style.backgroundColor = '#1e293b';
        modalContent.style.padding = '2rem';
        modalContent.style.borderRadius = '0.5rem';
        modalContent.style.maxWidth = '500px';
        modalContent.style.width = '90%';
        modalContent.style.position = 'relative';

        // Create title element
        const titleElement = document.createElement('h2');
        titleElement.style.color = '#ffffff';
        titleElement.style.marginTop = '0';
        titleElement.style.marginBottom = '1rem';

        // Create message element
        const messageElement = document.createElement('div');
        messageElement.style.color = '#94a3b8';
        messageElement.style.lineHeight = '1.6';
        messageElement.style.marginBottom = '1.5rem';

        // Create OK button
        const okButton = document.createElement('button');
        okButton.textContent = 'OK';
        okButton.style.padding = '0.5rem 1.5rem';
        okButton.style.backgroundColor = '#f97316';
        okButton.style.color = 'white';
        okButton.style.border = 'none';
        okButton.style.borderRadius = '0.25rem';
        okButton.style.cursor = 'pointer';
        okButton.onclick = function () {
            modal.style.display = 'none';
        };

        // Assemble the modal
        modalContent.appendChild(titleElement);
        modalContent.appendChild(messageElement);
        modalContent.appendChild(okButton);
        modal.appendChild(modalContent);
        document.body.appendChild(modal);
    }

    // Update modal content
    const titleElement = modal.querySelector('h2');
    const messageElement = modal.querySelector('div[style*="line-height: 1.6"]');

    if (titleElement) titleElement.textContent = title;
    if (messageElement) messageElement.textContent = message;

    // Show the modal
    modal.style.display = 'flex';

    // Close modal when clicking outside
    modal.onclick = function (event) {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    };

    return modal;
}

// Prepare auction (redirect to pre-auction countdown)
function prepareAuction() {
    console.log('Preparing auction...');

    // Check if there's an active auction
    const currentAuctionStatus = localStorage.getItem('currentAuctionStatus');
    if (currentAuctionStatus === 'RUNNING') {
        showModal('Auction in Progress', 'An auction is already running. Redirecting to live auction...');
        setTimeout(() => {
            window.location.href = 'admin-dashboard.html';
        }, 2000);
        return;
    }

    // Check if team preferences are available
    const preferences = JSON.parse(localStorage.getItem('teamOwnerPreferences') || '[]');
    if (preferences.length > 0) {
        loadTeamPreferences();
        showModal('Team Preferences Available', `Found ${preferences.length} team owner preferences. Please review and set the auction bidding time before starting.`);
        return;
    }

    // No preferences yet, start auction directly
    showModal('Starting Auction', 'Starting auction without countdown...');
    setTimeout(() => {
        startAuction();
    }, 1500);

    if (typeof logActivity === 'function') {
        logActivity('Prepare Auction', 'Initiated auction start flow', 'admin');
    }
}

// Start auction (for live auction management)
function startAuction() {
    console.log('Starting auction...');
    const bidTime = localStorage.getItem('auctionBidTime') || 20;

    // Update auction status
    localStorage.setItem('currentAuctionStatus', 'RUNNING');
    localStorage.setItem('auctionStartTime', new Date().toISOString());

    showModal('Auction Started!', `The auction is now live with ${bidTime}-second bidding rounds.`);
    if (typeof logActivity === 'function') {
        logActivity('Auction Started', `Bid time: ${bidTime}s`, 'admin');
    }
}

// Pause auction
function pauseAuction() {
    console.log('Pausing auction...');

    const currentStatus = localStorage.getItem('currentAuctionStatus');
    if (currentStatus === 'RUNNING') {
        localStorage.setItem('currentAuctionStatus', 'PAUSED');
        updateAuctionControls();

        showModal('Auction Paused', 'The auction has been paused. All team owners have been notified.');
        if (typeof logActivity === 'function') {
            logActivity('Auction Paused', '', 'admin');
        }
    }
}

// Resume auction
function resumeAuction() {
    console.log('Resuming auction...');

    localStorage.setItem('currentAuctionStatus', 'RUNNING');
    updateAuctionControls();

    showModal('Auction Resumed', 'The auction has resumed. All team owners have been notified.');
    if (typeof logActivity === 'function') {
        logActivity('Auction Resumed', '', 'admin');
    }
}

// End auction
function endAuction() {
    console.log('Ending auction...');

    if (confirm('Are you sure you want to end the auction? This action cannot be undone.')) {
        localStorage.setItem('currentAuctionStatus', 'ENDED');
        localStorage.setItem('auctionEndTime', new Date().toISOString());

        updateAuctionControls();

        showModal('Auction Ended', 'The auction has concluded. Final results will be calculated and all team owners will be notified.');

        // Redirect to results page after delay
        setTimeout(() => {
            // In a real app, redirect to results page
            alert('Redirecting to auction results...');
        }, 3000);

        if (typeof logActivity === 'function') {
            logActivity('Auction Ended', '', 'admin');
        }
    }
}

// Load team owner preferences
function loadTeamPreferences() {
    const preferences = JSON.parse(localStorage.getItem('teamOwnerPreferences') || '[]');

    if (preferences.length === 0) {
        document.getElementById('preferencesGrid').innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: #64748b;">
                <i class="fas fa-users" style="font-size: 3rem; margin-bottom: 1rem;"></i>
                <p>No team owner preferences submitted yet.</p>
                <p>Team owners will submit their preferred bidding times when the auction starts.</p>
            </div>
        `;
        return;
    }

    const preferencesGrid = document.getElementById('preferencesGrid');
    preferencesGrid.innerHTML = '';

    preferences.forEach(preference => {
        const preferenceCard = document.createElement('div');
        preferenceCard.className = 'preference-card';

        const submittedDate = new Date(preference.submittedAt);
        preferenceCard.innerHTML = `
            <div class="team-name">${preference.teamName}</div>
            <div class="preference-time">${preference.preferredBidTime}s</div>
            <div class="preference-label">Preferred Bidding Time</div>
            <div class="submitted-time">Submitted: ${submittedDate.toLocaleTimeString()}</div>
        `;

        preferencesGrid.appendChild(preferenceCard);
    });

    // Show preferences section
    document.getElementById('teamPreferencesSection').style.display = 'block';
}

// Set auction bidding time based on admin decision
function setAuctionBidTime() {
    const selectedTime = document.querySelector('input[name="adminBidTime"]:checked');
    if (!selectedTime) {
        showModal('Selection Required', 'Please select a bidding time for the auction.');
        return;
    }

    const bidTime = parseInt(selectedTime.value);

    // Store admin's decision
    localStorage.setItem('auctionBidTime', bidTime);

    // Update current auction data
    const currentAuctionData = JSON.parse(localStorage.getItem('currentAuctionData') || '{}');
    currentAuctionData.bidTimeLimit = bidTime;
    localStorage.setItem('currentAuctionData', JSON.stringify(currentAuctionData));

    showModal('Bidding Time Set!', `Auction bidding time has been set to ${bidTime} seconds per bid. All team owners will be notified.`);

    // Hide preferences section and show normal dashboard
    setTimeout(() => {
        document.getElementById('teamPreferencesSection').style.display = 'none';

        // Notify all team owners about the final decision
        localStorage.setItem('adminBidTimeDecision', new Date().toISOString());

        console.log('Admin set auction bidding time:', bidTime + ' seconds');
    }, 2000);

    if (typeof logActivity === 'function') {
        logActivity('Bid Time Set', `Time: ${bidTime}s`, 'admin');
    }
}

// Check if team preferences are available (for admin)
function checkTeamPreferences() {
    const preferences = JSON.parse(localStorage.getItem('teamOwnerPreferences') || '[]');
    if (preferences.length > 0) {
        loadTeamPreferences();
    }
}

// Initialize auction controls on page load
function updateAuctionControls() {
    const status = localStorage.getItem('currentAuctionStatus') || 'NOT_STARTED';
    const startBtn = document.getElementById('startAuctionBtn');
    const pauseBtn = document.getElementById('pauseAuctionBtn');
    const resumeBtn = document.getElementById('resumeAuctionBtn');
    const endBtn = document.getElementById('endAuctionBtn');

    if (!pauseBtn || !resumeBtn || !endBtn) return;

    // Hide all buttons by default
    if (startBtn) startBtn.style.display = 'none';
    pauseBtn.style.display = 'none';
    resumeBtn.style.display = 'none';
    endBtn.style.display = 'none';

    // Show buttons based on status
    if (status === 'NOT_STARTED') {
        if (startBtn) startBtn.style.display = 'inline-block';
    } else if (status === 'RUNNING') {
        pauseBtn.style.display = 'inline-block';
        endBtn.style.display = 'inline-block';
    } else if (status === 'PAUSED') {
        resumeBtn.style.display = 'inline-block';
        endBtn.style.display = 'inline-block';
    } else if (status === 'ENDED') {
        // No controls shown when ended
    }
}

document.addEventListener('DOMContentLoaded', function () {
    console.log('Admin dashboard loading...'); // Debug log

    // Update controls based on current auction status
    updateAuctionControls();

    // Load initial data
    loadTeamPreferences();

    // Set up event listeners
    document.getElementById('auctionBidTime')?.addEventListener('change', setupAdminBidTimeSelection);
    document.getElementById('setBidTimeBtn')?.addEventListener('click', setAuctionBidTime);

    // Set up admin bid time selection
    setupAdminBidTimeSelection();

    // Set up pagination event listeners (currently undefined)
    // setupPaginationEventListeners();

    // Set initial page size from localStorage if available
    const savedPageSize = localStorage.getItem('activityLogPageSize');
    if (savedPageSize) {
        activityLogPageSize = parseInt(savedPageSize, 10);
        const pageSizeSelect = document.getElementById('activityLogPageSize');
        if (pageSizeSelect) {
            pageSizeSelect.value = activityLogPageSize;
        }
    }

    // Log initial admin activity
    logActivity('Admin logged in', 'Admin accessed the dashboard', 'admin');
});

// Setup admin bid time selection
function setupAdminBidTimeSelection() {
    const adminTimeOptions = document.querySelectorAll('input[name="adminBidTime"]');
    adminTimeOptions.forEach(option => {
        option.addEventListener('change', function () {
            // Update visual selection
            document.querySelectorAll('.time-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            this.closest('.time-option').classList.add('selected');
        });
    });
}

// Tab switching for responses
function showResponsesTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });

    // Deactivate all tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    // Show the selected tab content
    document.getElementById(`${tabName}-tab`).classList.add('active');

    // Activate the clicked tab button
    const activeBtn = Array.from(document.querySelectorAll('.tab-btn')).find(btn =>
        btn.getAttribute('onclick').includes(tabName)
    );
    if (activeBtn) activeBtn.classList.add('active');

    // Load data for the selected tab if not already loaded
    if (tabName === 'players') {
        loadPlayerRegistrations();
    } else if (tabName === 'team-owners') {
        loadTeamOwnerRegistrations();
    }
}

// Helper to handle authentication errors
function handleAuthError(error) {
    if (error.message.includes('Not authenticated') || error.message.includes('401')) {
        showModal('Session Expired', 'Your session has expired. Redirecting to login page...');
        setTimeout(() => {
            sessionStorage.clear();
            localStorage.clear();
            window.location.href = '/';
        }, 2000);
        return true;
    }
    return false;
}

// Load player registrations
async function loadPlayerRegistrations(page = playerCurrentPage, pageSize = playerPageSize) {
    const tbody = document.getElementById('playerResponses');
    if (!tbody) return;

    try {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 2rem; color: #94a3b8;">
                    Loading player registrations...
                </td>
            </tr>
        `;

        const skip = (page - 1) * pageSize;
        let url = `/api/users?skip=${skip}&limit=${pageSize}&user_type=player`;
        if (currentViewEventId) {
            url += `&event_id=${currentViewEventId}`;
        }

        const response = await apiFetch(url, {
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
        });

        if (response.status === 401) {
            handleAuthError(new Error('Not authenticated'));
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const players = data.users || [];
        playerTotalCount = data.total || 0;
        playerCurrentPage = page;
        playerPageSize = pageSize;

        if (players.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; padding: 2rem; color: #94a3b8;">No player registrations found</td>
                </tr>
            `;
        } else {
            tbody.innerHTML = '';
            players.forEach(player => {
                // Format date to show full date and time
                let formattedDate = 'N/A';
                if (player.created_at) {
                    const date = new Date(player.created_at);
                    formattedDate = date.toLocaleString('en-US', {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: true
                    });
                }

                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>
                        <a href="javascript:void(0)" onclick="viewPlayerFullDetails(${player.user_id})" style="color: #3b82f6; text-decoration: none; font-weight: 500; transition: color 0.2s;" onmouseover="this.style.color='#60a5fa'" onmouseout="this.style.color='#3b82f6'">
                            ${player.first_name ? `${player.first_name} ${player.last_name || ''}` : (player.username || 'N/A')}
                        </a>
                        ${player.first_name && player.username ? `<div style="font-size: 12px; color: #64748b;">@${player.username}</div>` : ''}
                    </td>
                    <td>${player.email || 'N/A'}</td>
                    <td>${player.phone || 'N/A'}</td>
                    <td>${player.event_id || 'N/A'}</td>
                    <td>${formattedDate}</td>
                    <td>
                        <button class="admin-btn-action" onclick="deletePlayer(${player.user_id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                `;
                tbody.appendChild(row);
            });
        }

        updatePlayerPagination();

    } catch (error) {
        console.error('Error loading player registrations:', error);
        if (handleAuthError(error)) return;
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 2rem; color: #ef4444;">
                    Error loading player registrations: ${error.message}
                </td>
            </tr>
        `;
    }
}

// Update player pagination UI
function updatePlayerPagination() {
    const totalPages = Math.ceil(playerTotalCount / playerPageSize);
    const start = (playerCurrentPage - 1) * playerPageSize + 1;
    const end = Math.min(playerCurrentPage * playerPageSize, playerTotalCount);

    document.getElementById('playerPaginationInfo').textContent =
        `Showing ${start}-${end} of ${playerTotalCount}`;
    document.getElementById('playerPageNumber').textContent =
        `Page ${playerCurrentPage} of ${totalPages || 1}`;

    document.getElementById('playerPrevPage').disabled = playerCurrentPage <= 1;
    document.getElementById('playerNextPage').disabled = playerCurrentPage >= totalPages;
}

// Sort players by Event ID
function sortPlayersByEventId() {
    playerSortByEventId = true;
    playerEventIdSortAscending = !playerEventIdSortAscending;

    // Log the sort action
    const sortOrder = playerEventIdSortAscending ? 'ascending' : 'descending';
    logSortAction('Event ID', sortOrder);

    // Update sort icon
    const sortIcon = document.getElementById('eventIdSortIcon');
    if (sortIcon) {
        sortIcon.className = playerEventIdSortAscending ? 'fas fa-sort-up' : 'fas fa-sort-down';
    }

    // Get all rows from tbody
    const tbody = document.getElementById('playerResponses');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr'));

    // Sort rows by Event ID (4th column, index 3)
    rows.sort((a, b) => {
        const aEventId = a.cells[3]?.textContent.trim();
        const bEventId = b.cells[3]?.textContent.trim();

        // Handle N/A values - put them at the end
        if (aEventId === 'N/A' && bEventId === 'N/A') return 0;
        if (aEventId === 'N/A') return 1;
        if (bEventId === 'N/A') return -1;

        // Parse as numbers for proper sorting
        const aNum = parseInt(aEventId) || 0;
        const bNum = parseInt(bEventId) || 0;

        return playerEventIdSortAscending ? aNum - bNum : bNum - aNum;
    });

    // Clear tbody and append sorted rows
    tbody.innerHTML = '';
    rows.forEach(row => tbody.appendChild(row));
}

// Populate event filter dropdown
async function populateEventFilterDropdown() {
    try {
        const response = await apiFetch('/api/events', {
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) return;

        const events = await response.json();
        const playerDropdown = document.getElementById('eventFilterDropdown');
        const teamOwnerDropdown = document.getElementById('teamOwnerEventFilterDropdown');

        // Populate player filter dropdown
        if (playerDropdown) {
            playerDropdown.innerHTML = '<option value="">All Events</option>';
            events.forEach(event => {
                const option = document.createElement('option');
                option.value = event.event_id;
                option.textContent = `Event ${event.event_id}: ${event.title}`;
                playerDropdown.appendChild(option);
            });
        }

        // Populate team owner filter dropdown
        if (teamOwnerDropdown) {
            teamOwnerDropdown.innerHTML = '<option value="">All Events</option>';
            events.forEach(event => {
                const option = document.createElement('option');
                option.value = event.event_id;
                option.textContent = `Event ${event.event_id}: ${event.title}`;
                teamOwnerDropdown.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading events for filter:', error);
    }
}

// Filter players by event
function filterPlayersByEvent(eventId) {
    // Store the selected event filter
    currentViewEventId = eventId ? parseInt(eventId) : null;

    // Log the filter action
    const eventText = eventId ? `Event ${eventId}` : 'All Events';
    logFilterAction('Players', eventText);

    // Reload player registrations with the filter
    loadPlayerRegistrations(1, playerPageSize);
}

// Activity logging wrappers for admin actions
function logAndViewSection(sectionName) {
    logActivity(`Viewed ${sectionName}`, `Admin navigated to ${sectionName} section`, 'admin');
}

function logFilterAction(filterType, filterValue) {
    logActivity(`Applied Filter`, `Filtered ${filterType} by: ${filterValue}`, 'admin');
}

function logSortAction(sortField, sortOrder) {
    logActivity(`Sorted Data`, `Sorted by ${sortField} (${sortOrder})`, 'admin');
}

function logPaginationAction(page, section) {
    logActivity(`Changed Page`, `Navigated to page ${page} in ${section}`, 'admin');
}

// Filter team owners by event
function filterTeamOwnersByEvent(eventId) {
    // Store the selected event filter
    currentViewEventId = eventId ? parseInt(eventId) : null;

    // Log the filter action
    const eventText = eventId ? `Event ${eventId}` : 'All Events';
    logFilterAction('Team Owners', eventText);

    // Reload team owner registrations with the filter
    loadTeamOwnerRegistrations(1, teamOwnerPageSize);
}

// Load team owner registrations
async function loadTeamOwnerRegistrations(page = teamOwnerCurrentPage, pageSize = teamOwnerPageSize) {
    const tbody = document.getElementById('teamOwnerResponses');
    if (!tbody) return;

    try {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" style="text-align: center; padding: 2rem; color: #94a3b8;">
                    Loading team owner registrations...
                </td>
            </tr>
        `;

        const skip = (page - 1) * pageSize;
        let url = `/api/users?skip=${skip}&limit=${pageSize}&user_type=team_owner`;
        if (currentViewEventId) {
            url += `&event_id=${currentViewEventId}`;
        }
        
        // Add cache-busting timestamp to prevent browser from returning stale list after deletion
        url += (url.includes('?') ? '&' : '?') + `_t=${new Date().getTime()}`;

        const response = await apiFetch(url, {
            headers: { 
                'Content-Type': 'application/json',
                'Cache-Control': 'no-cache, no-store, must-revalidate'
            },
            credentials: 'include',
            cache: 'no-store'
        });

        if (response.status === 401) {
            handleAuthError(new Error('Not authenticated'));
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const teamOwners = data.users || [];
        teamOwnerTotalCount = data.total || 0;
        teamOwnerCurrentPage = page;
        teamOwnerPageSize = pageSize;

        if (teamOwners.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 2rem; color: #94a3b8;">No team owner registrations found</td>
                </tr>
            `;
        } else {
            tbody.innerHTML = '';
            teamOwners.forEach(owner => {
                const row = document.createElement('tr');
                row.id = `team-owner-row-${owner.user_id}`;
                const status = owner.is_active ? 'Active' : 'Pending';

                // Format date with time
                let formattedDate = 'N/A';
                if (owner.created_at) {
                    const date = new Date(owner.created_at);
                    formattedDate = date.toLocaleString('en-US', {
                        month: '2-digit',
                        day: '2-digit',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: true
                    });
                }

                // Escape owner name to prevent JS string breaking
                const ownerName = (owner.owner_name || owner.username || 'User').replace(/'/g, "\\'");
                
                let actions = '';
                if (!owner.is_active) {
                    actions = `<button onclick="approveUser(${owner.user_id}, '${ownerName}')" class="action-btn" style="background-color: #10b981; color: white; border: none; padding: 0.25rem 0.5rem; border-radius: 0.25rem; cursor: pointer;">Approve</button>`;
                }
                
                // Add delete button for all team owners
                actions += `<button onclick="deleteTeamOwner(${owner.user_id}, '${ownerName}')" class="action-btn" style="background-color: #ef4444; color: white; border: none; padding: 0.25rem 0.5rem; border-radius: 0.25rem; cursor: pointer; margin-left: 0.25rem;">Delete</button>`;

                row.innerHTML = `
                    <td onclick="viewTeamOwnerFullDetails(${owner.user_id})" style="cursor: pointer; color: #3b82f6;">${owner.team_name || 'N/A'}</td>
                    <td>${owner.email || 'N/A'}</td>
                    <td>${owner.phone || 'N/A'}</td>
                    <td onclick="viewTeamOwnerFullDetails(${owner.user_id})" style="cursor: pointer; color: #3b82f6;">${owner.owner_name || 'N/A'}</td>
                    <td>${owner.event_id || 'N/A'}</td>
                    <td>${formattedDate}</td>
                    <td><span class="status-badge ${status.toLowerCase()}">${status}</span></td>
                    <td>
                        <div style="display: flex; gap: 0.5rem; align-items: center;">
                            ${actions}
                            <button onclick="viewTeamOwnerFullDetails(${owner.user_id})" style="background: transparent; border: 1px solid #475569; color: #cbd5e1; border-radius: 4px; padding: 4px 8px; cursor: pointer;">
                                <i class="fas fa-eye"></i>
                            </button>
                        </div>
                    </td>
                `;
                tbody.appendChild(row);
            });
        }

        updateTeamOwnerPagination();

    } catch (error) {
        console.error('Error loading team owner registrations:', error);
        if (handleAuthError(error)) return;
        tbody.innerHTML = `
            <tr>
                <td colspan="8" style="text-align: center; padding: 2rem; color: #ef4444;">
                    Error loading team owner registrations: ${error.message}
                </td>
            </tr>
        `;
    }
}

// Approve User Function
async function approveUser(userId, currentName) {
    const confirmed = confirm(`Are you sure you want to approve the registration for ${currentName}?`);
    if (!confirmed) return;

    try {
        const response = await apiFetch(`/api/admin/users/${userId}/approve`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({}) // password is now optional; keeps the one set during registration
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to approve user');
        }

        alert('User approved successfully!');
        loadTeamOwnerRegistrations(); // Reload list
    } catch (error) {
        console.error('Error approving user:', error);
        alert(`Error: ${error.message}`);
    }
}

// Delete Player Function
async function deletePlayer(userId) {
    if (!confirm('Are you sure you want to delete this player? This action cannot be undone.')) return;
    try {
        const response = await apiFetch(`/api/admin/users/${userId}/delete`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete player');
        }
        alert('Player deleted successfully!');
        loadPlayerRegistrations();
    } catch (error) {
        console.error('Error deleting player:', error);
        alert(`Error: ${error.message}`);
    }
}

// Delete Team Owner Function
async function deleteTeamOwner(userId, currentName) {
    // Confirm deletion with warning about cascade deletion
    const confirmed = confirm(
        `Are you sure you want to delete ${currentName}?\n\n` +
        `This will:\n` +
        `• Delete the team owner account\n` +
        `• Cascade delete all linked staff members (managers/analysts)\n` +
        `• Delete all teams and related data\n\n` +
        `This action cannot be undone.`
    );
    
    if (!confirmed) return;

    try {
        const response = await apiFetch(`/api/admin/users/${userId}/delete`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete team owner');
        }

        const result = await response.json();
        
        let message = `Team owner ${currentName} deleted successfully!`;
        if (result.deleted_staff_count > 0) {
            message += `\n\nAlso deleted ${result.deleted_staff_count} linked staff members.`;
        }
        
        alert(message);
        
        const rowToRemove = document.getElementById(`team-owner-row-${userId}`);
        if (rowToRemove) {
            rowToRemove.remove();
        }
        
        loadTeamOwnerRegistrations(); // Reload list
    } catch (error) {
        console.error('Error deleting team owner:', error);
        alert(`Error: ${error.message}`);
    }
}

// Update team owner pagination UI
function updateTeamOwnerPagination() {
    const totalPages = Math.ceil(teamOwnerTotalCount / teamOwnerPageSize);
    const start = (teamOwnerCurrentPage - 1) * teamOwnerPageSize + 1;
    const end = Math.min(teamOwnerCurrentPage * teamOwnerPageSize, teamOwnerTotalCount);

    document.getElementById('teamOwnerPaginationInfo').textContent =
        `Showing ${start}-${end} of ${teamOwnerTotalCount}`;
    document.getElementById('teamOwnerPageNumber').textContent =
        `Page ${teamOwnerCurrentPage} of ${totalPages || 1}`;

    document.getElementById('teamOwnerPrevPage').disabled = teamOwnerCurrentPage <= 1;
    document.getElementById('teamOwnerNextPage').disabled = teamOwnerCurrentPage >= totalPages;
}

// Initialize pagination event listeners
function initializePaginationListeners() {
    // Player pagination
    document.getElementById('playerPageSize')?.addEventListener('change', (e) => {
        playerPageSize = parseInt(e.target.value);
        playerCurrentPage = 1;
        logActivity('Changed Page Size', `Set player page size to ${playerPageSize}`, 'admin');
        loadPlayerRegistrations();
    });

    document.getElementById('playerPrevPage')?.addEventListener('click', () => {
        if (playerCurrentPage > 1) {
            logPaginationAction(playerCurrentPage - 1, 'Player Registrations');
            loadPlayerRegistrations(playerCurrentPage - 1);
        }
    });

    document.getElementById('playerNextPage')?.addEventListener('click', () => {
        const totalPages = Math.ceil(playerTotalCount / playerPageSize);
        if (playerCurrentPage < totalPages) {
            logPaginationAction(playerCurrentPage + 1, 'Player Registrations');
            loadPlayerRegistrations(playerCurrentPage + 1);
        }
    });

    // Team owner pagination
    document.getElementById('teamOwnerPageSize')?.addEventListener('change', (e) => {
        teamOwnerPageSize = parseInt(e.target.value);
        teamOwnerCurrentPage = 1;
        logActivity('Changed Page Size', `Set team owner page size to ${teamOwnerPageSize}`, 'admin');
        loadTeamOwnerRegistrations();
    });

    document.getElementById('teamOwnerPrevPage')?.addEventListener('click', () => {
        if (teamOwnerCurrentPage > 1) {
            logPaginationAction(teamOwnerCurrentPage - 1, 'Team Owner Registrations');
            loadTeamOwnerRegistrations(teamOwnerCurrentPage - 1);
        }
    });

    document.getElementById('teamOwnerNextPage')?.addEventListener('click', () => {
        const totalPages = Math.ceil(teamOwnerTotalCount / teamOwnerPageSize);
        if (teamOwnerCurrentPage < totalPages) {
            logPaginationAction(teamOwnerCurrentPage + 1, 'Team Owner Registrations');
            loadTeamOwnerRegistrations(teamOwnerCurrentPage + 1);
        }
    });
}

// Activity logging functions
let activityLogs = JSON.parse(localStorage.getItem('adminActivityLogs') || '[]');
let currentAdminUserId = null;

// Sort and filter state
let currentSortOrder = 'newest';
let currentFilter = 'all';

// Pagination state
let currentPage = 1;
let pageSize = 10;
let totalPages = 1;

function logActivity(action, details, userType = null) {
    const timestamp = new Date().toISOString();
    const logEntry = {
        timestamp,
        action,
        details,
        userType: userType || getUserTypeFromAction(action) // Auto-detect user type from action
    };
    activityLogs.push(logEntry);
    try {
        localStorage.setItem('adminActivityLogs', JSON.stringify(activityLogs));
    } catch (e) {
        // If storage is full, keep last 500 entries
        activityLogs = activityLogs.slice(-500);
        localStorage.setItem('adminActivityLogs', JSON.stringify(activityLogs));
    }

    // Send log entry to backend for persistent storage
    sendActivityLogToServer(logEntry);

    displayActivityLogs();
}

async function fetchCurrentAdmin() {
    try {
        const response = await apiFetch('/api/me', {
            credentials: 'include',
            headers: {
                'Accept': 'application/json'
            }
        });
        if (!response.ok) {
            console.error(`[API HTTP Error] fetchCurrentAdmin failed with status: ${response.status}`);
            return;
        }
        const data = await response.json();
        if (data && typeof data.user_id !== 'undefined') {
            currentAdminUserId = data.user_id;
        }
    } catch (error) {
        console.error('Failed to fetch current admin info:', error);
    }
}

async function sendActivityLogToServer(logEntry) {
    try {
        const response = await apiFetch('/api/activity-logs', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action_type: logEntry.action,
                action_description: logEntry.details || '',
                entity_type: null,
                entity_id: null,
                ip_address: null,
                user_agent: navigator.userAgent
            })
        });
        if (!response.ok) {
            console.error(`[API HTTP Error] sendActivityLogToServer failed with status: ${response.status}`);
        }
    } catch (error) {
        console.error('Failed to send activity log to server:', error);
    }
}

async function loadActivityLogsFromServer() {
    try {
        const response = await apiFetch(`/api/activity-logs?skip=0&limit=500`, {
            credentials: 'include',
            headers: {
                'Accept': 'application/json'
            }
        });
        if (!response.ok) {
            console.error(`[API HTTP Error] loadActivityLogsFromServer failed with status: ${response.status}`);
            return;
        }
        const data = await response.json();
        const logs = Array.isArray(data.logs) ? data.logs : [];

        // Map backend logs into the existing activityLogs structure
        activityLogs = logs.map(log => ({
            timestamp: log.created_at || new Date().toISOString(),
            action: log.action_type || '',
            details: log.action_description || '',
            userType: getUserTypeFromAction(log.action_type || '')
        }));

        try {
            localStorage.setItem('adminActivityLogs', JSON.stringify(activityLogs));
        } catch (e) {
            // Ignore storage errors here; UI will still work from memory
        }

        displayActivityLogs();
    } catch (error) {
        console.error('Failed to load activity logs from server:', error);
    }
}

// Helper function to determine user type from action
function getUserTypeFromAction(action) {
    if (action.includes('Admin') || action.includes('Event Created') || action.includes('Event Updated') ||
        action.includes('Event Deleted') || action.includes('Auction') || action.includes('Bid Time') ||
        action.includes('Players Modal') || action.includes('Edit Event Modal') || action.includes('Live Link')) {
        return 'admin';
    } else if (action.includes('Team Owner') || action.includes('Squad') || action.includes('Bid Won') ||
        action.includes('Contact Admin') || action.includes('Registration Completed')) {
        return 'team_owner';
    } else if (action.includes('Player') || action.includes('Profile Update') || action.includes('View Events') ||
        action.includes('View Analytics') || action.includes('Registered')) {
        return 'player';
    }
    return 'admin'; // Default to admin for unknown actions
}

// Helper function to update existing logs with userType information
function updateExistingLogsWithUserType() {
    const logs = JSON.parse(localStorage.getItem('adminActivityLogs') || '[]');
    let updated = false;

    logs.forEach(log => {
        if (!log.userType) {
            log.userType = getUserTypeFromAction(log.action);
            updated = true;
        }
    });

    if (updated) {
        localStorage.setItem('adminActivityLogs', JSON.stringify(logs));
        activityLogs = logs;
    }
}

// Initialize sort and filter controls
function initializeSortAndFilter() {
    // Set initial filter button state
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const filterType = this.getAttribute('data-filter');
            setFilter(filterType);
        });
    });

    // Set initial sort order
    const sortSelect = document.getElementById('sortOrder');
    if (sortSelect) {
        sortSelect.addEventListener('change', applySortAndFilter);
    }
}

// Helper function to get user type badge HTML
function getUserTypeBadge(userType) {
    const badges = {
        admin: '<span style="background: #3b82f6; color: white; padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-size: 0.625rem; margin-right: 0.5rem;">ADMIN</span>',
        team_owner: '<span style="background: #10b981; color: white; padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-size: 0.625rem; margin-right: 0.5rem;">OWNER</span>',
        player: '<span style="background: #f59e0b; color: white; padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-size: 0.625rem; margin-right: 0.5rem;">PLAYER</span>'
    };
    return badges[userType] || '';
}

// Apply sort and filter
function applySortAndFilter() {
    const sortSelect = document.getElementById('sortOrder');
    if (sortSelect) {
        activityLogSort = sortSelect.value;
    }

    // Filter is updated by setFilter function

    activityLogCurrentPage = 1; // Reset to first page
    displayActivityLogs();
}

// Set filter and update UI
function setFilter(filterType) {
    activityLogFilter = filterType;
    activityLogCurrentPage = 1; // Reset to first page when changing filter

    // Update button states
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.filter === filterType) {
            btn.classList.add('active');
        }
    });

    // Apply filter using latest data from server
    displayActivityLogs();
}

function clearActivityLog() {
    if (confirm('Are you sure you want to clear all activity logs? This action cannot be undone.')) {
        // Log the clear action before clearing
        if (typeof logActivity === 'function') {
            logActivity('Activity Log Cleared', `Cleared ${activityLogs.length} log entries`, 'admin');
        }
        activityLogs = [];
        localStorage.setItem('adminActivityLogs', JSON.stringify(activityLogs));
        displayActivityLogs();
        showModal('Activity Log Cleared', 'All activity logs have been cleared.');
    }
}
// Activity Log State
let activityLogCurrentPage = 1;
let activityLogPageSize = 10;
let activityLogTotalCount = 0;
let activityLogSort = 'newest';
let activityLogFilter = 'all';

// Display activity logs
async function displayActivityLogs() {
    const tableBody = document.querySelector('#activityLogTable tbody');
    const noLogsMessage = document.getElementById('noLogsMessage');

    if (!tableBody || !noLogsMessage) return; // HTML not present on this page

    // Show loading state
    tableBody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 2rem; color: #94a3b8;">Loading activity logs...</td></tr>';
    noLogsMessage.style.display = 'none';

    try {
        // Build query string
        const skip = (activityLogCurrentPage - 1) * activityLogPageSize;
        const queryParams = new URLSearchParams({
            skip: skip,
            limit: activityLogPageSize,
            sort_by: activityLogSort,
            filter_by: activityLogFilter
        });

        const response = await apiFetch(`/api/activity-logs?${queryParams}`);
        if (!response.ok) {
            throw new Error('Failed to fetch activity logs');
        }

        const data = await response.json();
        const logs = data.logs;
        activityLogTotalCount = data.total;

        tableBody.innerHTML = '';

        if (logs.length === 0) {
            noLogsMessage.style.display = 'block';
            updateActivityLogPagination();
            return;
        }

        logs.forEach(log => {
            const row = document.createElement('tr');

            // Format date
            const date = new Date(log.created_at);
            const formattedDate = date.toLocaleString();

            // Format action type badge
            let actionClass = 'bg-gray-100 text-gray-800';
            if (log.action_type.includes('LOGIN')) actionClass = 'bg-green-100 text-green-800';
            else if (log.action_type.includes('ERROR')) actionClass = 'bg-red-100 text-red-800';
            else if (log.action_type.includes('ADMIN')) actionClass = 'bg-purple-100 text-purple-800';

            // Format details
            let details = log.action_description;
            if (log.user_info) {
                details += ` <span style="color: #64748b; font-size: 0.75rem;">(User: ${log.user_info.username})</span>`;
            }

            row.innerHTML = `
                <td>${formattedDate}</td>
                <td><span style="padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 600; background-color: #f1f5f9; color: #475569;">${log.action_type}</span></td>
                <td>${details}</td>
            `;
            tableBody.appendChild(row);
        });

        updateActivityLogPagination();

    } catch (error) {
        console.error('Error loading activity logs:', error);
        tableBody.innerHTML = '<tr><td colspan="3" style="text-align: center; padding: 2rem; color: #ef4444;">Error loading logs. Please try again.</td></tr>';
    }
}

// Refresh activity log
function refreshActivityLog() {
    displayActivityLogs();
}

// Update activity log pagination controls
function updateActivityLogPagination() {
    const totalPages = Math.ceil(activityLogTotalCount / activityLogPageSize);
    const startItem = activityLogTotalCount === 0 ? 0 : (activityLogCurrentPage - 1) * activityLogPageSize + 1;
    const endItem = Math.min(activityLogCurrentPage * activityLogPageSize, activityLogTotalCount);

    // Update info text
    const infoElement = document.getElementById('activityLogInfo');
    if (infoElement) {
        infoElement.textContent = `Showing ${startItem}-${endItem} of ${activityLogTotalCount}`;
    }

    // Update page number
    const pageNumberElement = document.getElementById('activityLogPageNumber');
    if (pageNumberElement) {
        pageNumberElement.textContent = `Page ${activityLogCurrentPage}`;
    }

    // Update buttons state
    const prevBtn = document.getElementById('activityLogPrevBtn');
    const nextBtn = document.getElementById('activityLogNextBtn');

    if (prevBtn) prevBtn.disabled = activityLogCurrentPage <= 1;
    if (nextBtn) nextBtn.disabled = activityLogCurrentPage >= totalPages || totalPages === 0;
}

// Change activity log page
function changeActivityLogPage(delta) {
    const totalPages = Math.ceil(activityLogTotalCount / activityLogPageSize);
    const newPage = activityLogCurrentPage + delta;

    if (newPage >= 1 && (totalPages === 0 || newPage <= totalPages)) {
        activityLogCurrentPage = newPage;
        displayActivityLogs();
    }
}

// Change activity log page size
function changeActivityLogPageSize(size) {
    activityLogPageSize = parseInt(size);
    activityLogCurrentPage = 1; // Reset to first page
    localStorage.setItem('activityLogPageSize', size);
    displayActivityLogs();
}

// -------------------------
// Event Management Actions
// -------------------------

// Store current event ID for actions
let currentEventId = null;

// Add players to event (first-come-first-serve)
async function addPlayersToEvent() {
    if (!currentEventId) {
        showModal('Error', 'No event selected');
        return;
    }

    try {
        const response = await apiFetch(`/events/${currentEventId}/add-players`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to add players');
        }

        const data = await response.json();
        showModal('Success', data.message);

        // Log activity
        if (typeof logActivity === 'function') {
            logActivity('Players Added to Event', `Added ${data.added_count} players`, 'admin');
        }
    } catch (error) {
        console.error('Error adding players:', error);
        showModal('Error', error.message);
    }
}

// Open Add Team Owner Modal
function addTeamOwnersToEvent() {
    if (!currentEventId) {
        showModal('Error', 'No event selected');
        return;
    }
    document.getElementById('addTeamOwnerModal').classList.add('active');
}

function closeAddTeamOwnerModal() {
    document.getElementById('addTeamOwnerModal').classList.remove('active');
    document.getElementById('addTeamOwnerForm').reset();
}

async function submitAddTeamOwner() {
    if (!currentEventId) {
        showModal('Error', 'No event selected');
        return;
    }

    const ownerData = {
        owner_name: document.getElementById('newOwnerName').value,
        team_name: document.getElementById('newTeamName').value,
        email: document.getElementById('newOwnerEmail').value,
        phone: document.getElementById('newOwnerPhone').value,
        address: document.getElementById('newOwnerAddress').value,
        username: document.getElementById('newOwnerUsername').value,
        password: document.getElementById('newOwnerPassword').value,
        event_id: currentEventId
    };

    // Basic validation
    if (!ownerData.owner_name || !ownerData.team_name || !ownerData.email || !ownerData.username || !ownerData.password) {
        showModal('Error', 'Please fill in all required fields');
        return;
    }

    try {
        const response = await apiFetch(`/events/${currentEventId}/create-team-owner`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(ownerData),
            credentials: 'include'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to create team owner');
        }

        const data = await response.json();
        showModal('Success', data.message);
        closeAddTeamOwnerModal();

        // Log activity
        if (typeof logActivity === 'function') {
            logActivity('Team Owner Created', `Created team owner ${ownerData.owner_name} for event`, 'admin');
        }
    } catch (error) {
        console.error('Error creating team owner:', error);
        showModal('Error', error.message);
    }
}

// Make event live
async function makeEventLive() {
    if (!currentEventId) {
        showModal('Error', 'No event selected');
        return;
    }

    try {
        const response = await apiFetch(`/events/${currentEventId}/make-live`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to make event live');
        }

        const data = await response.json();

        // Log activity
        if (typeof logActivity === 'function') {
            logActivity('Event Made Live', `Event: ${data.title}`, 'admin');
        }

        // Show success
        showModal('Success', 'Event is now live!');

        // Reload events
        loadEvents();
    } catch (error) {
        console.error('Error making event live:', error);
        showModal('Error', error.message);
    }
}

// View live auction
async function viewLiveAuction() {
    if (!currentEventId) {
        showModal('Error', 'No event selected');
        return;
    }

    try {
        const response = await apiFetch(`/events/${currentEventId}/live-auction`);

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Failed to get auction details');
        }

        const data = await response.json();

        if (data.has_auction) {
            // Redirect to auction page
            window.location.href = data.auction_url;
        } else {
            showModal('Info', data.message);
        }
    } catch (error) {
        console.error('Error viewing auction:', error);
        showModal('Error', error.message);
    }
}

// View players for current event
async function viewEventPlayers() {
    if (!currentEventId) {
        showModal('Error', 'No event selected');
        return;
    }

    const modal = document.getElementById('eventPlayersModal');
    const grid = document.getElementById('eventPlayersGrid');
    const title = document.getElementById('eventPlayersModalTitle');

    // Get event title
    const event = eventsData.find(e => e.event_id == currentEventId);
    if (event) {
        title.textContent = `Players for ${event.title}`;
    }

    // Show modal and loading state
    modal.classList.add('active');
    grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #94a3b8;">Loading players...</div>';

    try {
        // Fetch players for this event
        const response = await apiFetch(`/api/users?user_type=player&event_id=${currentEventId}&limit=1000`, {
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const players = data.users || [];

        if (players.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #94a3b8;">No players registered for this event yet.</div>';
            return;
        }

        // Render player cards
        grid.innerHTML = players.map(player => createPlayerCard(player)).join('');

    } catch (error) {
        console.error('Error loading event players:', error);
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #ef4444;">Error loading players: ${error.message}</div>`;
    }
}

// Helper function to generate sport skills HTML dynamically
function generateSportSkillsHTML(player) {
    const sportIcons = {
        'Cricket': 'fa-running',
        'Football': 'fa-futbol',
        'Basketball': 'fa-basketball-ball',
        'Tennis': 'fa-table-tennis',
        'Badminton': 'fa-shuttlecock',
        'Hockey': 'fa-hockey-puck',
        'Volleyball': 'fa-volleyball-ball',
        'Baseball': 'fa-baseball-ball',
        'Golf': 'fa-golf-ball'
    };

    let skillsHTML = '';

    // Check if player has sport_ratings array (new format)
    if (player.sport_ratings && Array.isArray(player.sport_ratings)) {
        player.sport_ratings.forEach(sport => {
            const icon = sportIcons[sport.sport_name] || 'fa-trophy';
            skillsHTML += `
                <div class="skill-card">
                    <i class="fas ${icon}"></i>
                    <span>${sport.sport_name}</span>
                    <div class="rating-circle">${sport.rating || 'N/A'}</div>
                </div>
            `;
        });
    } else {
        // Fallback to old format (direct properties)
        const sports = [
            { name: 'Cricket', rating: player.cricket_rating },
            { name: 'Football', rating: player.football_rating },
            { name: 'Basketball', rating: player.basketball_rating }
        ];

        sports.forEach(sport => {
            if (sport.rating !== null && sport.rating !== undefined) {
                const icon = sportIcons[sport.name] || 'fa-trophy';
                skillsHTML += `
                    <div class="skill-card">
                        <i class="fas ${icon}"></i>
                        <span>${sport.name}</span>
                        <div class="rating-circle">${sport.rating}</div>
                    </div>
                `;
            }
        });
    }

    return skillsHTML || '<p style="color: #94a3b8;">No sport ratings available</p>';
}

// View full details of a player
async function viewPlayerFullDetails(playerId) {
    try {
        // Fetch full player details
        const response = await apiFetch(`/api/users/${playerId}`, {
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
        });

        if (!response.ok) throw new Error('Failed to fetch player details');

        const player = await response.json();

        // Populate modal
        const modal = document.getElementById('playerFullDetailsModal');
        const content = document.getElementById('playerFullDetailsContent');

        // Format dates
        const dob = player.date_of_birth ? new Date(player.date_of_birth).toLocaleDateString() : 'N/A';
        const joined = new Date(player.created_at).toLocaleDateString();

        content.innerHTML = `
            <div style="display: flex; gap: 2rem; margin-bottom: 2rem;">
                <div style="width: 150px; height: 150px; border-radius: 50%; overflow: hidden; background: #334155; border: 4px solid #3b82f6; flex-shrink: 0; display: flex; align-items: center; justify-content: center;">
                    ${player.profile_image_url
                ? `<img src="${player.profile_image_url}" alt="${player.first_name}" style="width: 100%; height: 100%; object-fit: cover;">`
                : `<i class="fas fa-user" style="font-size: 4rem; color: #94a3b8;"></i>`}
                </div>
                <div style="flex: 1;">
                    <h2 style="margin: 0 0 0.5rem 0; color: #f8fafc; font-size: 2rem;">${player.first_name || ''} ${player.last_name || ''}</h2>
                    <p style="color: #94a3b8; font-size: 1.1rem; margin-bottom: 1rem;">@${player.username}</p>
                    <div style="display: flex; gap: 1rem;">
                        <span class="status-badge ${player.is_active ? 'active' : 'inactive'}">${player.is_active ? 'Active' : 'Inactive'}</span>
                        <span class="status-badge ${player.is_verified ? 'verified' : 'pending'}">${player.is_verified ? 'Verified' : 'Unverified'}</span>
                    </div>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 2rem;">
                <!-- Personal Info -->
                <div class="info-group">
                    <h3 style="color: #cbd5e1; border-bottom: 1px solid #334155; padding-bottom: 0.5rem;">Personal Information</h3>
                    <div class="info-row"><label>Email:</label> <span>${player.email}</span></div>
                    <div class="info-row"><label>Phone:</label> <span>${player.phone || 'N/A'}</span></div>
                    <div class="info-row"><label>Date of Birth:</label> <span>${dob}</span></div>
                    <div class="info-row"><label>Gender:</label> <span>${player.gender || 'N/A'}</span></div>
                    <div class="info-row"><label>Height:</label> <span>${player.height_cm ? player.height_cm + ' cm' : 'N/A'}</span></div>
                    <div class="info-row"><label>Weight:</label> <span>${player.weight_kg ? player.weight_kg + ' kg' : 'N/A'}</span></div>
                </div>
                
                <!-- Location & Other -->
                <div class="info-group">
                    <h3 style="color: #cbd5e1; border-bottom: 1px solid #334155; padding-bottom: 0.5rem;">Location & Meta</h3>
                    <div class="info-row"><label>Address:</label> <span>${player.address || 'N/A'}</span></div>
                    <div class="info-row"><label>City:</label> <span>${player.city || 'N/A'}</span></div>
                    <div class="info-row"><label>State:</label> <span>${player.state || 'N/A'}</span></div>
                    <div class="info-row"><label>Country:</label> <span>${player.country || 'N/A'}</span></div>
                    <div class="info-row"><label>Pincode:</label> <span>${player.pincode || 'N/A'}</span></div>
                    <div class="info-row"><label>Joined:</label> <span>${joined}</span></div>
                </div>
            </div>
            
            <!-- Skills -->
            <div style="margin-top: 2rem;">
                <h3 style="color: #cbd5e1; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; margin-bottom: 1rem;">Sports Skills</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem;">
                    ${(() => {
                const sportIcons = {
                    'Cricket': 'fa-running', 'Football': 'fa-futbol', 'Basketball': 'fa-basketball-ball',
                    'Tennis': 'fa-table-tennis', 'Badminton': 'fa-shuttlecock', 'Hockey': 'fa-hockey-puck',
                    'Volleyball': 'fa-volleyball-ball', 'Baseball': 'fa-baseball-ball', 'Golf': 'fa-golf-ball'
                };

                let html = '';

                // Use dynamic sports_skills if available
                if (player.sports_skills && player.sports_skills.length > 0) {
                    player.sports_skills.forEach(skill => {
                        const icon = sportIcons[skill.sport_name] || 'fa-trophy';
                        html += `
                            <div class="skill-card">
                                <i class="fas ${icon}"></i>
                                <span>${skill.sport_name}</span>
                                <div class="rating-circle">${skill.rating}</div>
                            </div>
                        `;
                    });
                } else {
                    // Fallback to legacy fields if sports_skills is missing
                    const sports = [
                        { name: 'Cricket', rating: player.cricket_rating },
                        { name: 'Football', rating: player.football_rating },
                        { name: 'Basketball', rating: player.basketball_rating },
                        { name: 'Tennis', rating: player.tennis_rating },
                        { name: 'Badminton', rating: player.badminton_rating },
                        { name: 'Hockey', rating: player.hockey_rating },
                        { name: 'Volleyball', rating: player.volleyball_rating },
                        { name: 'Baseball', rating: player.baseball_rating },
                        { name: 'Golf', rating: player.golf_rating }
                    ];

                    sports.forEach(sport => {
                        if (sport.rating !== null && sport.rating !== undefined) {
                            const icon = sportIcons[sport.name] || 'fa-trophy';
                            html += `
                                <div class="skill-card">
                                    <i class="fas ${icon}"></i>
                                    <span>${sport.name}</span>
                                    <div class="rating-circle">${sport.rating}</div>
                                </div>
                            `;
                        }
                    });
                }

                return html || '<p style="color: #94a3b8;">No sport ratings available</p>';
            })()}
                </div>
            </div>
            
             <div style="margin-top: 2rem;">
                <h3 style="color: #cbd5e1; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; margin-bottom: 1rem;">Bio</h3>
                <p style="color: #94a3b8; line-height: 1.6;">${player.bio || 'No status bio provided.'}</p>
             </div>
        `;

        modal.style.display = 'block';

    } catch (error) {
        console.error('Error fetching full details:', error);
        showModal('Error', 'Could not load player details: ' + error.message);
    }
}


// View full details of a team owner
async function viewTeamOwnerFullDetails(ownerId) {
    try {
        const response = await apiFetch(`/api/users/${ownerId}`, {
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
        });

        if (!response.ok) throw new Error('Failed to fetch team owner details');

        const owner = await response.json();

        const modal = document.getElementById('teamOwnerFullDetailsModal');
        const content = document.getElementById('teamOwnerFullDetailsContent');

        const joined = new Date(owner.created_at).toLocaleDateString();

        content.innerHTML = `
            <div style="margin-bottom: 2rem;">
                <h2 style="margin: 0 0 0.5rem 0; color: #f8fafc; font-size: 2rem;">${owner.owner_name || 'N/A'}</h2>
                <div style="display: flex; gap: 1rem; align-items: center;">
                    <p style="color: #94a3b8; font-size: 1.1rem; margin: 0;">Owner of <strong style="color: #3b82f6;">${owner.team_name || 'N/A'}</strong></p>
                    <span class="status-badge ${owner.is_active ? 'active' : 'inactive'}">${owner.is_active ? 'Active' : 'Pending'}</span>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 2rem;">
                <!-- Contact Info -->
                <div class="info-group">
                    <h3 style="color: #cbd5e1; border-bottom: 1px solid #334155; padding-bottom: 0.5rem;">Contact Information</h3>
                    <div class="info-row"><label>Email:</label> <span>${owner.email}</span></div>
                    <div class="info-row"><label>Phone:</label> <span>${owner.phone || 'N/A'}</span></div>
                    <div class="info-row"><label>Address:</label> <span>${owner.address || 'N/A'}</span></div>
                </div>
                
                <!-- Team & Meta -->
                <div class="info-group">
                    <h3 style="color: #cbd5e1; border-bottom: 1px solid #334155; padding-bottom: 0.5rem;">Team & Account</h3>
                    <div class="info-row"><label>Company:</label> <span>${owner.company_name || 'N/A'}</span></div>
                    <div class="info-row"><label>Event ID:</label> <span>${owner.event_id || 'N/A'}</span></div>
                    <div class="info-row"><label>Wallet Balance:</label> <span style="color: #22c55e; font-weight: bold;">₹${parseFloat(owner.wallet_balance || 0).toLocaleString()}</span></div>
                    <div class="info-row"><label>Registered:</label> <span>${joined}</span></div>
                </div>
            </div>
            
            ${!owner.is_active ? `
                <div style="margin-top: 2rem; padding: 1rem; background: #1e293b; border-radius: 0.5rem; text-align: center;">
                    <p style="color: #94a3b8; margin-bottom: 1rem;">This team owner account is pending approval.</p>
                     <button onclick="approveUser(${owner.user_id}, '${(owner.owner_name || '').replace(/'/g, "\\'")}')" style="background: #10b981; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 0.5rem; cursor: pointer; font-weight: 600;">
                        Approve Account
                    </button>
                </div>
            ` : ''}
        `;

        modal.style.display = 'block';

    } catch (error) {
        console.error('Error fetching team owner details:', error);
        showModal('Error', 'Could not load details: ' + error.message);
    }
}


function createPlayerCard(player) {
    // Format date of birth
    const dob = player.date_of_birth ? new Date(player.date_of_birth).toLocaleDateString() : 'N/A';

    // Calculate age if DOB exists
    let age = 'N/A';
    if (player.date_of_birth) {
        const birthDate = new Date(player.date_of_birth);
        const today = new Date();
        age = today.getFullYear() - birthDate.getFullYear();
        const m = today.getMonth() - birthDate.getMonth();
        if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
            age--;
        }
    }

    return `
        <div style="background: #1e293b; border-radius: 0.5rem; overflow: hidden; border: 1px solid #334155; display: flex; flex-direction: column; cursor: pointer; transition: transform 0.2s;" onclick="viewPlayerFullDetails(${player.user_id})" onmouseover="this.style.transform='translateY(-4px)'" onmouseout="this.style.transform='translateY(0)'">
            <div style="padding: 1.5rem; display: flex; flex-direction: column; align-items: center; border-bottom: 1px solid #334155; background: #0f172a;">
                <div style="width: 80px; height: 80px; border-radius: 50%; overflow: hidden; margin-bottom: 1rem; border: 2px solid #3b82f6; display: flex; align-items: center; justify-content: center; background: #334155;">
                    ${player.profile_image_url
            ? `<img src="${player.profile_image_url}" alt="${player.first_name || 'Player'}" style="width: 100%; height: 100%; object-fit: cover;">`
            : `<i class="fas fa-user" style="font-size: 2.5rem; color: #94a3b8;"></i>`}
                </div>
                <h3 style="margin: 0; color: #f8fafc; font-size: 1.125rem;">${player.first_name || ''} ${player.last_name || ''}</h3>
                <p style="margin: 0.25rem 0 0; color: #94a3b8; font-size: 0.875rem;">@${player.username}</p>
            </div>
            <div style="padding: 1.5rem; flex: 1;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; font-size: 0.875rem;">
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Email</span>
                        <span style="color: #e2e8f0; word-break: break-all;">${player.email}</span>
                    </div>
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Phone</span>
                        <span style="color: #e2e8f0;">${player.phone || 'N/A'}</span>
                    </div>
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Age</span>
                        <span style="color: #e2e8f0;">${age}</span>
                    </div>
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Gender</span>
                        <span style="color: #e2e8f0;">${player.gender || 'N/A'}</span>
                    </div>
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Height</span>
                        <span style="color: #e2e8f0;">${player.height_cm ? player.height_cm + ' cm' : 'N/A'}</span>
                    </div>
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Weight</span>
                        <span style="color: #e2e8f0;">${player.weight_kg ? player.weight_kg + ' kg' : 'N/A'}</span>
                    </div>
                    <div style="grid-column: 1/-1;">
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Location</span>
                        <span style="color: #e2e8f0;">${player.city || ''}, ${player.state || ''}</span>
                    </div>
                </div>
                
                ${player.bio ? `
                <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #334155;">
                    <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Bio</span>
                    <p style="margin: 0; color: #cbd5e1; font-size: 0.875rem; line-height: 1.5;">${player.bio}</p>
                </div>
                ` : ''}
            </div>
        </div>
    `;
}

function closeEventPlayersModal() {
    document.getElementById('eventPlayersModal').classList.remove('active');
}

// View team owners for current event
async function viewEventTeamOwners() {
    if (!currentEventId) {
        showModal('Error', 'No event selected');
        return;
    }

    const modal = document.getElementById('eventTeamOwnersModal');
    const grid = document.getElementById('eventTeamOwnersGrid');
    const title = document.getElementById('eventTeamOwnersModalTitle');

    // Get event title
    const event = eventsData.find(e => e.event_id == currentEventId);
    if (event) {
        title.textContent = `Team Owners for ${event.title}`;
    }

    // Show modal and loading state
    modal.classList.add('active');
    grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #94a3b8;">Loading team owners...</div>';

    try {
        // Fetch team owners for this event
        const response = await apiFetch(`/api/users?user_type=team_owner&event_id=${currentEventId}&limit=1000`, {
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include'
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        const teamOwners = data.users || [];

        if (teamOwners.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #94a3b8;">No team owners registered for this event yet.</div>';
            return;
        }

        // Render team owner cards
        grid.innerHTML = teamOwners.map(owner => createTeamOwnerCard(owner)).join('');

    } catch (error) {
        console.error('Error loading event team owners:', error);
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #ef4444;">Error loading team owners: ${error.message}</div>`;
    }
}

function createTeamOwnerCard(owner) {
    // Get team logo or default
    const teamLogo = owner.team_logo_url;

    return `
        <div style="background: #1e293b; border-radius: 0.5rem; overflow: hidden; border: 1px solid #334155; display: flex; flex-direction: column;">
            <div style="padding: 1.5rem; display: flex; flex-direction: column; align-items: center; border-bottom: 1px solid #334155; background: #0f172a;">
                <div style="width: 80px; height: 80px; border-radius: 50%; overflow: hidden; margin-bottom: 1rem; border: 2px solid #8b5cf6; display: flex; align-items: center; justify-content: center; background: #334155;">
                    ${teamLogo
            ? `<img src="${teamLogo}" alt="${owner.team_name || 'Team'}" style="width: 100%; height: 100%; object-fit: cover;">`
            : `<i class="fas fa-users" style="font-size: 2.5rem; color: #94a3b8;"></i>`}
                </div>
                <h3 style="margin: 0; color: #f8fafc; font-size: 1.125rem;">${owner.team_name || 'Team Name'}</h3>
                <p style="margin: 0.25rem 0 0; color: #94a3b8; font-size: 0.875rem;">Owner: ${owner.owner_name || owner.username}</p>
            </div>
            <div style="padding: 1.5rem; flex: 1;">
                <div style="display: grid; grid-template-columns: 1fr; gap: 1rem; font-size: 0.875rem;">
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Email</span>
                        <span style="color: #e2e8f0; word-break: break-all;">${owner.email}</span>
                    </div>
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Phone</span>
                        <span style="color: #e2e8f0;">${owner.phone || owner.contact_number || 'N/A'}</span>
                    </div>
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Username</span>
                        <span style="color: #e2e8f0;">@${owner.username}</span>
                    </div>
                    ${owner.address ? `
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Address</span>
                        <span style="color: #e2e8f0;">${owner.address}</span>
                    </div>
                    ` : ''}
                    ${owner.team_bio ? `
                    <div>
                        <span style="display: block; color: #64748b; margin-bottom: 0.25rem;">Team Bio</span>
                        <p style="margin: 0; color: #cbd5e1; font-size: 0.875rem; line-height: 1.5;">${owner.team_bio}</p>
                    </div>
                    ` : ''}
                </div>
            </div>
        </div>
    `;
}

function closeEventTeamOwnersModal() {
    document.getElementById('eventTeamOwnersModal').classList.remove('active');
}

// Support messages pagination state
let currentMessagePage = 1;
const messagesPerPage = 10;
let allMessages = [];

// Load messages
async function loadMessages() {
    try {
        const response = await fetch('/api/messages', {
            credentials: 'include'
        });
        if (response.ok) {
            allMessages = await response.json();

            // Apply sorting
            const sortBy = document.getElementById('messageSortSelect')?.value || 'date_desc';
            sortMessages(allMessages, sortBy);

            // Display messages with pagination
            displayMessages(allMessages);
        }
    } catch (error) {
        console.error('Error loading messages:', error);
    }
}

// Sort messages
function sortMessages(messages, sortBy) {
    switch (sortBy) {
        case 'date_desc':
            messages.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
            break;
        case 'date_asc':
            messages.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
            break;
        case 'unread':
            messages.sort((a, b) => (a.is_read === b.is_read) ? 0 : a.is_read ? 1 : -1);
            break;
        case 'team_name':
            messages.sort((a, b) => (a.team_name || '').localeCompare(b.team_name || ''));
            break;
    }
}

// Change message page
function changeMessagePage(direction) {
    const totalPages = Math.ceil(allMessages.length / messagesPerPage);
    currentMessagePage = Math.max(1, Math.min(currentMessagePage + direction, totalPages));
    displayMessages(allMessages);
}

function displayMessages(messages) {
    const container = document.getElementById('messagesContainer');
    const noMsg = document.getElementById('noMessages');

    if (!messages || messages.length === 0) {
        if (container) container.style.display = 'none';
        if (noMsg) noMsg.style.display = 'block';
        return;
    }

    if (container) container.style.display = 'block';
    if (noMsg) noMsg.style.display = 'none';
    if (container) container.innerHTML = '';

    messages.forEach(msg => {
        const item = document.createElement('div');
        item.style.borderBottom = '1px solid #e5e7eb';
        item.style.padding = '1rem';
        item.style.backgroundColor = msg.is_read ? '#f9fafb' : '#ffffff';
        item.style.opacity = msg.is_read ? '0.7' : '1';

        const date = new Date(msg.created_at).toLocaleString();

        const actionButton = msg.is_read
            ? `<span style="color: #10b981; font-size: 0.875rem;"><i class="fas fa-check"></i> Read</span>`
            : `<button onclick="markMessageRead(${msg.message_id})" style="color: #3b82f6; background: none; border: none; cursor: pointer; font-size: 0.875rem;">Mark as Read</button>`;

        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                <div>
                    <span style="font-weight: 600; color: #111827;">${msg.team_name || 'Unknown Team'}</span>
                    <span style="color: #64748b; font-size: 0.875rem; margin-left: 0.5rem;">(${msg.sender_name || 'User'})</span>
                </div>
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <div style="color: #94a3b8; font-size: 0.875rem;">${date}</div>
                    ${actionButton}
                </div>
            </div>
            <div style="font-weight: 500; color: #374151; margin-bottom: 0.25rem;">${msg.subject || 'No Subject'}</div>
            <div style="color: #4b5563;">${msg.content}</div>
        `;
        if (container) container.appendChild(item);
    });
}

// Mark message as read
async function markMessageRead(messageId) {
    try {
        const response = await fetch(`/api/messages/${messageId}/read`, {
            method: 'PUT',
            credentials: 'include'
        });

        if (response.ok) {
            // Refresh messages
            loadMessages();

            // Log activity
            if (typeof logActivity === 'function') {
                logActivity('Message Read', `Marked message ${messageId} as read`, 'admin');
            }
        } else {
            console.error('Failed to mark message as read');
            showModal('Error', 'Failed to mark message as read');
        }
    } catch (error) {
        console.error('Error marking message read:', error);
        showModal('Error', 'An error occurred while updating the message');
    }
}

// ----------------------------------------------------
// NEW DASHBOARD FUNCTIONS (Sports, Teams, Reports)
// ----------------------------------------------------

async function loadSports() {
    try {
        const response = await fetch('/api/sports');
        const data = await response.json();
        const sports = data.sports || data || [];
        const tbody = document.querySelector('#sportsTable tbody');
        const sportSelect = document.getElementById('editSportId');
        
        if (sportSelect) {
            sportSelect.innerHTML = '<option value="">Select a Sport...</option>';
        }
        
        if (!tbody) return;
        
        if (sports.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: #94a3b8;">No sports found.</td></tr>';
            return;
        }
        
        tbody.innerHTML = '';
        sports.forEach(sport => {
            // Populate the dropdown inside the Event Creation Modal
            if (sportSelect) {
                const opt = document.createElement('option');
                opt.value = sport.sport_id;
                opt.textContent = sport.name;
                sportSelect.appendChild(opt);
            }
            
            const tr = document.createElement('tr');
            
            // Serialize config to string safely for data attributes
            const sportData = btoa(unescape(encodeURIComponent(JSON.stringify(sport))));
            
            tr.innerHTML = `
                <td>${sport.sport_id}</td>
                <td><i class="${sport.icon_class} mr-2"></i> ${sport.name}</td>
                <td>${sport.description || 'N/A'}</td>
                <td>
                    <button class="admin-btn-action" style="background: linear-gradient(135deg, #00ffff 0%, #0080ff 100%); color: black;" onclick="openConfigureSportModal('${sportData}')"><i class="fas fa-cogs"></i> Configure</button>
                    <button class="admin-btn-action" onclick="deleteSport(${sport.sport_id})"><i class="fas fa-trash"></i> Delete</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading sports:', e);
    }
}

// State to hold dynamic categories for the modal
let currentSportCategories = [];

function openConfigureSportModal(sportDataB64) {
    try {
        const sport = JSON.parse(decodeURIComponent(escape(atob(sportDataB64))));
        document.getElementById('configureSportId').value = sport.sport_id;
        
        // Handle hidden values to preserve non-editable JSON structures
        document.getElementById('configRolesHidden').value = sport.roles_config ? JSON.stringify(sport.roles_config) : '';
        document.getElementById('configAttributesHidden').value = sport.attributes_schema ? JSON.stringify(sport.attributes_schema) : '';
        document.getElementById('configRulesHidden').value = sport.default_auction_rules ? JSON.stringify(sport.default_auction_rules) : '';
        
        // 1. Populate Team Budget
        const budgetInput = document.getElementById('configDefaultBudget');
        if (sport.default_auction_rules && sport.default_auction_rules.default_budget) {
            budgetInput.value = sport.default_auction_rules.default_budget;
        } else {
            budgetInput.value = ''; // Default to empty so admin sets it
        }

        // 2. Populate Player Categories
        currentSportCategories = [];
        if (sport.categories_config) {
            if (Array.isArray(sport.categories_config)) {
                // If stored as array: [{"name": "Diamond", "base_price": 50000}]
                currentSportCategories = [...sport.categories_config];
            } else if (typeof sport.categories_config === 'object') {
                // If stored as dictionary: {"diamond": 50000}
                for (const [key, value] of Object.entries(sport.categories_config)) {
                    // Capitalize dictionary keys for display (e.g. "diamond" -> "Diamond")
                    const displayName = key.charAt(0).toUpperCase() + key.slice(1);
                    currentSportCategories.push({
                        name: displayName,
                        base_price: value
                    });
                }
            }
        }
        
        renderSportCategories();
        
        // Clear add category inputs
        document.getElementById('newCategoryName').value = '';
        document.getElementById('newCategoryPrice').value = '';
        
        document.getElementById('configureSportModal').classList.add('active');
    } catch (e) {
        console.error("Error opening configure sport modal:", e);
        showModal('Error', 'Failed to load sport configuration.');
    }
}

function renderSportCategories() {
    const tbody = document.getElementById('configCategoriesTableBody');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    if (currentSportCategories.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center; color: #94a3b8; padding: 1rem;">No categories added yet.</td></tr>';
        return;
    }
    
    currentSportCategories.forEach((cat, index) => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = '1px solid #1e293b';
        tr.innerHTML = `
            <td style="padding: 0.75rem 0;">${cat.name}</td>
            <td style="padding: 0.75rem 0;">₹${cat.base_price.toLocaleString()}</td>
            <td style="padding: 0.75rem 0; text-align: right;">
                <button type="button" class="btn btn-outline-danger" style="padding: 0.25rem 0.5rem; font-size: 0.875rem;" onclick="deleteSportCategory(${index})">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function addSportCategory() {
    const nameInput = document.getElementById('newCategoryName');
    const priceInput = document.getElementById('newCategoryPrice');
    
    const name = nameInput.value.trim();
    const price = parseFloat(priceInput.value);
    
    if (!name) {
        showModal('Validation Error', 'Category name is required.');
        return;
    }
    
    if (isNaN(price) || price < 0) {
        showModal('Validation Error', 'Base price must be a valid number greater than or equal to 0.');
        return;
    }
    
    // Check for duplicates (case insensitive)
    const exists = currentSportCategories.some(cat => cat.name.toLowerCase() === name.toLowerCase());
    if (exists) {
        showModal('Validation Error', `Category "${name}" already exists.`);
        return;
    }
    
    currentSportCategories.push({
        name: name,
        base_price: price
    });
    
    renderSportCategories();
    
    // Clear inputs after successful add
    nameInput.value = '';
    priceInput.value = '';
}

function deleteSportCategory(index) {
    if (index >= 0 && index < currentSportCategories.length) {
        currentSportCategories.splice(index, 1);
        renderSportCategories();
    }
}

function closeConfigureSportModal() {
    document.getElementById('configureSportModal').classList.remove('active');
}

async function saveSportConfiguration() {
    const sportId = document.getElementById('configureSportId').value;
    
    // Validate Team Budget
    const budgetValue = parseFloat(document.getElementById('configDefaultBudget').value);
    if (isNaN(budgetValue) || budgetValue <= 0) {
        showModal('Validation Error', 'Team Budget is required and must be greater than 0.');
        return;
    }
    
    // Parse JSON safely from hidden inputs (preserves backend-provided configuration)
    const parseJSON = (id) => {
        const val = document.getElementById(id).value.trim();
        if (!val) return null;
        try {
            return JSON.parse(val);
        } catch (e) {
            console.error(`Invalid JSON in hidden field ${id}`, e);
            return null;
        }
    };
    
    try {
        const sportName = document.getElementById('configureSportNameDisplay').textContent.toLowerCase();
        
        // Read the preserved rules from the hidden input, or create a new object
        let rules = parseJSON('configRulesHidden') || {};
        // Update the specific values that the Admin has control over
        rules.default_budget = budgetValue;
        // Enforce the system default timer if it wasn't already set
        if (!rules.default_timer) rules.default_timer = 20;
        
        let roles = parseJSON('configRolesHidden');
        if (!roles || (Array.isArray(roles) && roles.length === 0)) {
            roles = ["Batsman", "Bowler", "All-Rounder", "Wicket-Keeper"];
        }
        
        let attributes = parseJSON('configAttributesHidden');
        if (!attributes || Object.keys(attributes).length === 0) {
            attributes = {
                "batting_style": ["Right-hand bat", "Left-hand bat"],
                "bowling_style": ["Right-arm fast", "Right-arm medium", "Right-arm spin", "Left-arm fast", "Left-arm medium", "Left-arm spin"]
            };
        }
        
        const payload = {
            roles_config: roles,
            attributes_schema: attributes,
            categories_config: currentSportCategories, // Send as array of objects
            default_auction_rules: rules
        };
        
        const response = await fetch(`/api/sports/${sportId}/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        if (data.success) {
            closeConfigureSportModal();
            loadSports();
            showModal('Success', 'Cricket configuration saved successfully.');
        } else {
            showModal('Error', data.error || 'Failed to save configuration');
        }
    } catch (e) {
        showModal('Error', e.message || 'An error occurred saving configuration.');
    }
}

async function deleteSport(id) {
    if(!confirm("Are you sure you want to delete this sport?")) return;
    try {
        const response = await fetch(`/api/admin/sports/${id}`, { method: 'DELETE' });
        if (response.ok) {
            loadSports();
            alert("Sport deleted successfully.");
        }
    } catch (e) {
        console.error(e);
        alert("Failed to delete sport.");
    }
}

async function loadTeams() {
    try {
        const response = await fetch('/api/admin/teams');
        const teams = await response.json();
        const tbody = document.querySelector('#teamsTable tbody');
        if (!tbody) return;
        
        if (teams.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color: #94a3b8;">No teams found.</td></tr>';
            return;
        }
        
        tbody.innerHTML = '';
        teams.forEach(t => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${t.team_id}</td>
                <td>${t.team_name}</td>
                <td>${t.owner_name}</td>
                <td>$${t.budget}M</td>
                <td>${t.manager_count}</td>
                <td>${t.analyst_count}</td>
                <td>
                    <button class="admin-btn-action" onclick="alert('View team coming soon!')"><i class="fas fa-eye"></i> View</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error('Error loading teams:', e);
    }
}

async function loadReports() {
    try {
        const response = await fetch('/api/dashboard/admin/stats');
        const stats = await response.json();
        
        const revEl = document.getElementById('reportTotalRevenue');
        if (revEl) revEl.textContent = `$${stats.auction_revenue || 0}M`;
        
        const teamEl = document.getElementById('reportTotalTeams');
        if (teamEl) teamEl.textContent = stats.total_teams || 0;
        
        const playerEl = document.getElementById('reportTotalPlayers');
        if (playerEl) playerEl.textContent = stats.total_players || 0;
        
        const soldEl = document.getElementById('reportSoldPlayers');
        if (soldEl) soldEl.textContent = stats.purchased_players || 0;
        
    } catch (e) {
        console.error('Error loading reports:', e);
    }
}

function openCreateSportModal() {
    const name = prompt("Enter Sport Name:");
    if (!name) return;
    const desc = prompt("Enter Description:");
    
    fetch('/api/admin/sports', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, description: desc })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            loadSports();
        } else {
            alert("Error creating sport");
        }
    })
    .catch(console.error);
}

// Consolidated DOMContentLoaded listener
document.addEventListener('DOMContentLoaded', function () {
    console.log('Admin dashboard loading...');

    // Check if user is authenticated via localStorage
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        console.log('No user found in localStorage, redirecting to login');
        window.location.replace('/');
        return;
    }

    const user = JSON.parse(userStr);
    console.log('Current user:', user);

    // Update welcome message with admin name
    const welcomeMessage = document.querySelector('.dashboard-header h1');
    if (welcomeMessage) {
        welcomeMessage.textContent = `Welcome, ${user.username || 'Admin'}`;
    }

    // Store username for display purposes
    sessionStorage.setItem('username', user.username || 'Admin');

    // Load events
    loadEvents();

    // Add event listener for the Add Sport button
    const addSportBtn = document.querySelector('.add-sport-btn');
    if (addSportBtn) {
        addSportBtn.addEventListener('click', addNewSport);
    }

    // Update existing logs to include userType information
    updateExistingLogsWithUserType();

    // Render activity logs on load
    if (typeof displayActivityLogs === 'function') {
        displayActivityLogs();
    }

    // Initialize sort and filter controls
    initializeSortAndFilter();

    // Update controls based on current auction status
    updateAuctionControls();

    // Load initial data
    loadTeamPreferences();

    // Set initial page size from localStorage if available
    const savedPageSize = localStorage.getItem('activityLogPageSize');
    if (savedPageSize) {
        activityLogPageSize = parseInt(savedPageSize, 10);
        const pageSizeSelect = document.getElementById('activityLogPageSize');
        if (pageSizeSelect) {
            pageSizeSelect.value = activityLogPageSize;
        }
    }

    // Log initial admin activity
    logActivity('Admin logged in', 'Admin accessed the dashboard', 'admin');

    // Initialize pagination listeners
    initializePaginationListeners();

    // Load registrations
    loadPlayerRegistrations();
    loadTeamOwnerRegistrations();

    // Set up event listeners for tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            // Remove active class from all buttons
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Hide all sections
            const tabId = this.getAttribute('data-tab');
            const sections = [
                'dashboardSection', 'sportsSection', 'teamsSection',
                'registrationsSection', 'teamOwnerRegistrationsSection',
                'auctionsSection', 'reportsSection'
            ];

            sections.forEach(secId => {
                const el = document.getElementById(secId);
                if (el) el.style.display = 'none';
            });

            // Also hide the manageEventsContainer if we aren't on dashboard
            const manageEvents = document.getElementById('manageEventsContainer');
            if (manageEvents) {
                manageEvents.style.display = (tabId === 'dashboard') ? 'block' : 'none';
            }

            // Show selected section
            if (tabId === 'dashboard') {
                const el = document.getElementById('dashboardSection');
                if (el) el.style.display = 'block';
                if (manageEvents) manageEvents.style.display = 'block';
            } else if (tabId === 'sports') {
                const el = document.getElementById('sportsSection');
                if (el) el.style.display = 'block';
                if (typeof loadSports === 'function') loadSports();
            } else if (tabId === 'teams') {
                const el = document.getElementById('teamsSection');
                if (el) el.style.display = 'block';
                if (typeof loadTeams === 'function') loadTeams();
            } else if (tabId === 'players') {
                const el = document.getElementById('registrationsSection');
                if (el) el.style.display = 'block';
                loadPlayerRegistrations();
            } else if (tabId === 'team-owners') {
                const el = document.getElementById('teamOwnerRegistrationsSection');
                if (el) el.style.display = 'block';
                loadTeamOwnerRegistrations();
            } else if (tabId === 'auctions') {
                const el = document.getElementById('auctionsSection');
                if (el) el.style.display = 'block';
            } else if (tabId === 'reports') {
                const el = document.getElementById('reportsSection');
                if (el) el.style.display = 'block';
                if (typeof loadReports === 'function') loadReports();
            }
        });
    });

    // Initialize system monitoring
    loadSystemStats();
    // Auto-refresh system stats every 3 seconds
    setInterval(loadSystemStats, 3000);

    // Fetch current admin info and load activity logs
    fetchCurrentAdmin();
    loadActivityLogsFromServer();
});

// Fetch current admin information from the backend
function fetchCurrentAdmin() {
    fetch('/api/me')
        .then(response => {
            if (!response.ok) {
                console.log('Not authenticated via API, redirecting to login');
                window.location.replace('/');
                throw new Error('Not authenticated');
            }
            return response.json();
        })
        .then(data => {
            if (data.user_type !== 'admin') {
                console.log('User is not an admin, redirecting to login');
                window.location.replace('/');
            } else {
                console.log('Admin authenticated successfully');
            }
        })
        .catch(error => {
            console.error('Auth error in fetchCurrentAdmin:', error);
        });
}

// --- Phase 1 & 2: Auction Preparation ---

let currentPrepEventId = null;
let auctionPrepPollingInterval = null;

function closeAuctionPrepModal() {
    const modal = document.getElementById('auctionPrepModal');
    if (modal) {
        modal.classList.remove('active');
    }
    if (auctionPrepPollingInterval) {
        clearInterval(auctionPrepPollingInterval);
        auctionPrepPollingInterval = null;
    }
}

// Attach close event to modal close button if it exists
document.addEventListener('DOMContentLoaded', () => {
    // Assuming there is a close button inside the modal
    const closeBtn = document.querySelector('#auctionPrepModal .close-modal');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeAuctionPrepModal);
    }
});

async function openAuctionPrepModal(eventId) {
    currentPrepEventId = eventId;
    const modal = document.getElementById('auctionPrepModal');
    const body = document.getElementById('auctionPrepBody');
    const subtitle = document.getElementById('auctionPrepSubtitle');

    modal.classList.add('active');
    
    // Add custom styling for the modal-content if needed to prevent overlap
    const modalContent = modal.querySelector('.modal-content');
    if (modalContent) {
        modalContent.style.display = 'flex';
        modalContent.style.flexDirection = 'column';
        modalContent.style.maxHeight = '90vh';
        modalContent.style.overflow = 'hidden';
        modalContent.classList.add('auction-prep-modal-content');
    }
    
    body.style.overflowY = 'auto';
    body.style.flex = '1';
    
    body.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem 0; color: var(--text-muted, #64748b);">
            <div style="width: 50px; height: 50px; border: 3px solid rgba(59, 130, 246, 0.2); border-top-color: #3b82f6; border-radius: 50%; animation: spin 1s linear infinite; margin-bottom: 1rem;"></div>
            <div style="font-weight: 500; letter-spacing: 0.5px;">GATHERING REGISTRATION DATA...</div>
        </div>
        <style>@keyframes spin { 100% { transform: rotate(360deg); } }</style>
    `;

    // Start polling loop
    if (auctionPrepPollingInterval) {
        clearInterval(auctionPrepPollingInterval);
    }
    
    await fetchAndRenderAuctionPrep();
    auctionPrepPollingInterval = setInterval(fetchAndRenderAuctionPrep, 5000);
}

async function fetchAndRenderAuctionPrep() {
    if (!currentPrepEventId) return;
    
    const modal = document.getElementById('auctionPrepModal');
    if (!modal || !modal.classList.contains('active')) {
        // Modal is closed, stop polling
        if (auctionPrepPollingInterval) {
            clearInterval(auctionPrepPollingInterval);
            auctionPrepPollingInterval = null;
        }
        return;
    }
    
    const body = document.getElementById('auctionPrepBody');
    const subtitle = document.getElementById('auctionPrepSubtitle');
    
    try {
        const response = await fetch(`/api/admin/events/${currentPrepEventId}/auction-prep`, {
            credentials: 'include',
            headers: { 'Accept': 'application/json' }
        });

        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
                if (auctionPrepPollingInterval) clearInterval(auctionPrepPollingInterval);
                alert("Your Admin session is no longer valid.");
                window.location.href = '/index.html';
                return;
            }
            const err = await response.json().catch(() => ({}));
            throw new Error(err.description || `Server error ${response.status}`);
        }

        const data = await response.json();
        const isReady = data.teams_count > 0 && data.players_count > 0 && data.all_teams_active === true;

        if (subtitle) {
            subtitle.innerHTML = `Review registrations for <strong style="color: var(--text-primary, white);">${data.event.title}</strong> before starting the live auction.`;
        }

        const html = `
            <div style="display: flex; flex-direction: column; gap: 1.5rem; padding-bottom: 1rem;">
                
                <!-- Stat Cards -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                    <div class="prep-stat-card prep-stat-teams">
                        <div class="prep-stat-icon"><i class="fas fa-users" style="font-size: 5rem;"></i></div>
                        <div class="prep-stat-label">Registered Teams</div>
                        <div class="prep-stat-value">${data.teams_count}</div>
                    </div>
                    
                    <div class="prep-stat-card prep-stat-players">
                        <div class="prep-stat-icon"><i class="fas fa-user" style="font-size: 5rem;"></i></div>
                        <div class="prep-stat-label">Registered Players</div>
                        <div class="prep-stat-value">${data.players_count}</div>
                    </div>
                </div>

                <!-- Registration Lists -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem;">
                    
                    <!-- Teams List -->
                    <div class="prep-list-card">
                        <div class="prep-list-header">
                            <h3 class="prep-list-title">
                                <span><i class="fas fa-shield-alt" style="color: var(--accent-green, #10b981); margin-right: 0.5rem;"></i> Teams</span>
                                <span class="prep-list-count">${data.teams_count}</span>
                            </h3>
                        </div>
                        <div class="prep-list-body">
                            ${data.teams.length === 0 ? '<div class="prep-empty-msg">No teams registered</div>' :
                              '<div style="display: flex; flex-direction: column; gap: 0.25rem;">' + data.teams.map(t => `
                                <div class="prep-list-item">
                                    <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
                                        <div style="display: flex; align-items: center; gap: 0.75rem;">
                                            <div class="prep-avatar prep-avatar-team">
                                                ${t.team_name.charAt(0).toUpperCase()}
                                            </div>
                                            <div>
                                                <div class="prep-item-title">${t.team_name}</div>
                                                <div class="prep-item-subtitle">${t.owner || 'Unknown Owner'}</div>
                                            </div>
                                        </div>
                                        <div>
                                            ${t.active 
                                                ? '<span style="color: #34d399; font-weight: bold; font-size: 0.85rem;">🟢 ACTIVE</span>'
                                                : '<span style="color: #f87171; font-weight: bold; font-size: 0.85rem;">🔴 INACTIVE</span>'
                                            }
                                        </div>
                                    </div>
                                </div>
                              `).join('') + '</div>'
                            }
                        </div>
                    </div>

                    <!-- Players List -->
                    <div class="prep-list-card">
                        <div class="prep-list-header">
                            <h3 class="prep-list-title">
                                <span><i class="fas fa-user-friends" style="color: var(--accent-blue, #3b82f6); margin-right: 0.5rem;"></i> Players</span>
                                <span class="prep-list-count">${data.players_count}</span>
                            </h3>
                        </div>
                        <div class="prep-list-body">
                            ${data.players.length === 0 ? '<div class="prep-empty-msg">No players registered</div>' :
                              '<div style="display: flex; flex-direction: column; gap: 0.25rem;">' + data.players.map(p => `
                                <div class="prep-list-item">
                                    <div style="display: flex; align-items: center; gap: 0.75rem;">
                                        <div class="prep-avatar prep-avatar-player">
                                            <i class="fas fa-user" style="font-size: 0.8rem;"></i>
                                        </div>
                                        <div>
                                            <div class="prep-item-title">${p.name}</div>
                                            <div class="prep-item-subtitle">Base Price: ₹${(p.base_price || 0).toLocaleString()}</div>
                                        </div>
                                    </div>
                                </div>
                              `).join('') + '</div>'
                            }
                        </div>
                    </div>

                </div>
                
                <!-- Status Bar -->
                ${isReady 
                    ? `<div style="margin-top: 0.5rem; padding: 1rem; border-radius: 0.5rem; background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.2); display: flex; align-items: center; gap: 1rem; color: #34d399;">
                        <i class="fas fa-check-circle fa-lg"></i>
                        <div>
                            <div style="font-weight: 600;">🟢 Auction Ready to Start</div>
                            <div style="font-size: 0.85rem; opacity: 0.8;">All registered team owners are online. The lobby is ready.</div>
                        </div>
                       </div>`
                    : (data.teams_count === 0 || data.players_count === 0)
                        ? `<div style="margin-top: 0.5rem; padding: 1rem; border-radius: 0.5rem; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); display: flex; align-items: center; gap: 1rem; color: #f87171;">
                            <i class="fas fa-exclamation-triangle fa-lg"></i>
                            <div>
                                <div style="font-weight: 600;">Action Required</div>
                                <div style="font-size: 0.85rem; opacity: 0.8;">You must have at least one active team and one player registered to begin the auction.</div>
                            </div>
                           </div>`
                        : `<div style="margin-top: 0.5rem; padding: 1rem; border-radius: 0.5rem; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.2); display: flex; align-items: center; gap: 1rem; color: #f59e0b;">
                            <i class="fas fa-hourglass-half fa-lg"></i>
                            <div>
                                <div style="font-weight: 600;">⚠ Waiting for Team Owners</div>
                                <div style="font-size: 0.85rem; opacity: 0.8;">${data.active_team_count} of ${data.teams_count} team owners are online. All registered team owners must be online before the auction can start.</div>
                            </div>
                           </div>`
                }
            </div>
        `;
        
        // Only update innerHTML if it has changed to prevent UI flickering during polling
        if (body.innerHTML !== html) {
            body.innerHTML = html;
        }

        const modalFooter = modal.querySelector('.modal-footer');
        if (modalFooter) {
            modalFooter.style.position = 'relative';
            modalFooter.style.background = 'var(--bg-card, rgba(15, 23, 42, 0.95))';
            modalFooter.style.borderTop = '1px solid var(--border-color, #334155)';
            modalFooter.style.zIndex = '10';
            modalFooter.style.padding = '1.25rem';
        }

        const proceedBtn = document.getElementById('btnProceedAuction');
        if (!isReady) {
            proceedBtn.disabled = true;
            proceedBtn.style.opacity = '0.5';
            proceedBtn.style.cursor = 'not-allowed';
            proceedBtn.style.background = '#475569';
            proceedBtn.title = (data.teams_count === 0 || data.players_count === 0) ? "You need at least 1 team and 1 player to start." : "All team owners must be online to proceed.";
        } else {
            proceedBtn.disabled = false;
            proceedBtn.style.opacity = '1';
            proceedBtn.style.cursor = 'pointer';
            proceedBtn.style.background = 'linear-gradient(135deg, #00ffff 0%, #0080ff 100%)';
            proceedBtn.style.color = '#000';
            proceedBtn.style.boxShadow = '0 4px 15px rgba(0, 128, 255, 0.4)';
            proceedBtn.title = "";
        }

    } catch (err) {
        console.error(err);
        body.innerHTML = `<div style="color: #ef4444; text-align: center; padding: 3rem 1rem;">
            <i class="fas fa-exclamation-circle fa-3x" style="margin-bottom: 1rem; opacity: 0.8;"></i>
            <h3 style="margin-bottom: 0.5rem;">Error Loading Data</h3>
            <p style="font-size: 0.875rem; opacity: 0.8;">${err.message}</p>
        </div>`;
    }
}

async function proceedWithAuction() {
    if (!currentPrepEventId) return;
    const proceedBtn = document.getElementById('btnProceedAuction');
    if (proceedBtn.disabled) return;
    
    proceedBtn.disabled = true;
    proceedBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Initializing...';

    // Stop polling
    if (auctionPrepPollingInterval) {
        clearInterval(auctionPrepPollingInterval);
        auctionPrepPollingInterval = null;
    }

    try {
        const response = await fetch(`/api/admin/events/${currentPrepEventId}/auction/initialize`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
                alert("Your Admin session is no longer valid. This usually happens if you logged into another account (like Team Owner) in a different tab. You will be redirected to the login page.");
                window.location.href = '/index.html';
                return;
            }
            if (response.status === 409) {
                const errData = await response.json();
                alert(errData.message || "Cannot start auction: Team owners are offline.");
                // Resume polling to see updates
                auctionPrepPollingInterval = setInterval(fetchAndRenderAuctionPrep, 5000);
                await fetchAndRenderAuctionPrep();
                return;
            }
            const rawText = await response.text();
            let errData = {};
            try { errData = JSON.parse(rawText); } catch(e) {}
            
            console.error("Auction initialization failed:", {
                status: response.status,
                rawResponse: rawText,
                parsedData: errData
            });
            
            const errMsg = errData.message || errData.description || rawText || 'Failed to initialize auction';
            throw new Error(`Server Error: ${errMsg}`);
        }

        const data = await response.json();
        
        if (!data.success) {
            console.error("Auction initialization returned success: false", data);
            throw new Error(data.message || 'Failed to initialize auction');
        }

        // Redirect to the real-time auction lobby
        window.location.href = `/templates/live-auction.html?id=${currentPrepEventId}`;

    } catch (err) {
        console.error("Proceed with auction error:", err);
        alert('Error: ' + err.message);
        proceedBtn.disabled = false;
        proceedBtn.innerHTML = 'Proceed With Auction';
        
        // Resume polling on error
        if (!auctionPrepPollingInterval) {
            auctionPrepPollingInterval = setInterval(fetchAndRenderAuctionPrep, 5000);
        }
    }
}

// Function to handle when an Admin selects a Sport during Event Creation
async function handleSportSelectionChange(sportId) {
    if (!sportId) return;

    try {
        const response = await fetch(`/api/sports/${sportId}`);
        const data = await response.json();
        
        if (data.success && data.sport) {
            const sport = data.sport;
            
            // Auto-fill Default Rules (Budget, Timer)
            if (sport.default_auction_rules) {
                const rules = sport.default_auction_rules;
                if (rules.default_budget) document.getElementById('editMaxBudget').value = rules.default_budget;
                if (rules.default_timer) document.getElementById('editBidTime').value = rules.default_timer;
            }
            
            // Auto-fill Base Prices from Categories Config
            if (sport.categories_config) {
                const cats = sport.categories_config;
                if (Array.isArray(cats)) {
                    // It's an Array (e.g. [{"name": "Diamond", "base_price": 50000}])
                    cats.forEach(cat => {
                        const name = cat.name.toLowerCase();
                        if (name === 'diamond') document.getElementById('editPriceDiamond').value = cat.base_price;
                        if (name === 'platinum') document.getElementById('editPricePlatinum').value = cat.base_price;
                        if (name === 'gold') document.getElementById('editPriceGold').value = cat.base_price;
                        if (name === 'silver') document.getElementById('editPriceSilver').value = cat.base_price;
                    });
                } else if (typeof cats === 'object') {
                    // It's a Dictionary (e.g. {"diamond": 50000})
                    if (cats.diamond) document.getElementById('editPriceDiamond').value = cats.diamond;
                    if (cats.platinum) document.getElementById('editPricePlatinum').value = cats.platinum;
                    if (cats.gold) document.getElementById('editPriceGold').value = cats.gold;
                    if (cats.silver) document.getElementById('editPriceSilver').value = cats.silver;
                }
            }
            
            console.log(`Auto-filled defaults for ${sport.name}`);
        }
    } catch (e) {
        console.error("Failed to load sport defaults:", e);
    }
}
