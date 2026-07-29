
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

// Player Dashboard JavaScript
document.addEventListener('DOMContentLoaded', function () {
    console.log('Player dashboard loading...');

    // Check if user is authenticated via localStorage
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        console.log('No user found in localStorage, redirecting to login');
        window.location.href = '/';
        return;
    }

    const user = JSON.parse(userStr);
    console.log('Current user:', user);

    // Check if user is player
    if (user.user_type !== 'player') {
        console.log('Access denied - user is not player');
        showModal('Access Denied', 'Please login as a player to access this page.');
        setTimeout(() => {
            window.location.href = '/';
        }, 2000);
        return;
    }

    // Load player data and initialize dashboard
    loadPlayerData();
    loadSkills();
    loadActivities();

    // Add event listeners for action buttons
    setupEventListeners();
});

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
        // Swallow errors to avoid blocking functionality
        console.warn('Failed to write admin activity log:', e);
    }

    // Also send activity to backend so it is stored in the database
    try {
        fetch('/api/activity-logs', {
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
            console.warn('Failed to send player activity log to server:', err);
        });
    } catch (err) {
        console.warn('Failed to send player activity log to server:', err);
    }
}

// Mock player data removed to enforce real DB usage
// Main initialization function
async function initializeDashboard() {
    console.log("Initializing Player Dashboard...");

    // Setup global state based on role
    currentRole = 'player';
    
    // UI Setup
    updateDateTime();
    setInterval(updateDateTime, 1000);
    setupSidebar();
    
    // Bind navigation buttons
    document.getElementById('profileNavBtn')?.addEventListener('click', () => switchSection('profile-section'));
    document.getElementById('eventsNavBtn')?.addEventListener('click', () => switchSection('events-section'));
    document.getElementById('messagesNavBtn')?.addEventListener('click', () => switchSection('messages-section'));
    document.getElementById('settingsNavBtn')?.addEventListener('click', () => switchSection('settings-section'));

    try {
        await loadPlayerData();
        await loadEvents();
        await loadMessages();
        setupActivityChart();
        setupPerformanceChart();
    } catch (e) {
        console.error("Dashboard initialization error", e);
    }
}

async function loadPlayerData() {
    try {
        const response = await fetch('/api/player/dashboard', {
            headers: { 'Accept': 'application/json' },
            credentials: 'include'
        });
        
        if (!response.ok) {
            throw new Error(`Failed to load player data: ${response.status}`);
        }
        
        const playerData = await response.json();
        
        // Populate DOM elements
        document.getElementById('playerNameMain').textContent = playerData.name || 'Unknown Player';
        document.getElementById('fullName').textContent = playerData.name || '-';
        document.getElementById('dateOfBirth').textContent = playerData.dateOfBirth ? new Date(playerData.dateOfBirth).toLocaleDateString() : '-';
        document.getElementById('age').textContent = playerData.age ? `${playerData.age} years` : '-';
        document.getElementById('gender').textContent = playerData.gender || '-';
        document.getElementById('email').textContent = playerData.email || '-';
        document.getElementById('phone').textContent = playerData.phone || '-';
        document.getElementById('location').textContent = playerData.location || '-';
        document.getElementById('experience').textContent = playerData.experience || '-';
        
        const tierElement = document.getElementById('playerTier');
        if (tierElement && playerData.tier) {
            tierElement.textContent = playerData.tier.charAt(0).toUpperCase() + playerData.tier.slice(1);
            tierElement.className = `player-tier tier-${playerData.tier.toLowerCase()}`;
        }
        
        // Update stats
        document.getElementById('eventsCount').textContent = playerData.eventsCount || 0;
        document.getElementById('auctionsWon').textContent = playerData.auctionsWon || 0;
        document.getElementById('avgRating').textContent = playerData.avgRating || 0;
        document.getElementById('currentValue').textContent = `₹${(playerData.currentValue || 0).toLocaleString()}`;
        
        // Update auction status
        const auctionStatusElement = document.getElementById('auctionStatus');
        if (auctionStatusElement) {
            const statusText = (playerData.activeAuctions > 0)
                ? `Active in ${playerData.activeAuctions} Auctions`
                : 'No Active Auctions';
            auctionStatusElement.innerHTML = `<i class="fas fa-gavel"></i> ${statusText}`;
            auctionStatusElement.className = `auction-status ${(playerData.activeAuctions > 0) ? 'status-active' : 'status-inactive'}`;
        }
        
        // Update performance metrics
        document.getElementById('totalEvents').textContent = playerData.totalEvents || 0;
        document.getElementById('successRate').textContent = `${playerData.successRate || 0}%`;
        document.getElementById('avgBid').textContent = `₹${(playerData.avgBid || 0).toLocaleString()}`;
        document.getElementById('highestBid').textContent = `₹${(playerData.highestBid || 0).toLocaleString()}`;
        document.getElementById('teamsInterested').textContent = playerData.teamsInterested || 0;
        document.getElementById('profileViews').textContent = playerData.profileViews || 0;
        
        // Update achievements
        document.getElementById('tournamentsWon').textContent = playerData.tournamentsWon || 0;
        document.getElementById('mvpAwards').textContent = playerData.mvpAwards || 0;
        document.getElementById('bestPlayerAwards').textContent = playerData.bestPlayerAwards || 0;
        document.getElementById('proContracts').textContent = playerData.proContracts || 0;
        
        const avatarElement = document.getElementById('playerAvatar');
        if (avatarElement) {
            if (playerData.avatar) {
                avatarElement.innerHTML = `<img src="${playerData.avatar}" alt="Player Avatar" style="width: 100%; height: 100%; border-radius: 50%; object-fit: cover;">`;
            } else {
                avatarElement.innerHTML = `<i class="fas fa-user"></i>`;
            }
        }
    } catch (error) {
        console.error('Error loading player data:', error);
    }
}

// Load and display sports skills from API
async function loadSkills() {
    try {
        const response = await fetch('/api/me');
        if (!response.ok) {
            throw new Error('Failed to fetch player data');
        }
        const playerData = await response.json();

        const skillsGrid = document.getElementById('skillsGrid');
        skillsGrid.innerHTML = '';

        // Create skills from API rating data
        const skills = [];
        if (playerData.cricket_rating) {
            skills.push({ sport: 'Cricket', icon: '🏏', rating: playerData.cricket_rating });
        }
        if (playerData.football_rating) {
            skills.push({ sport: 'Football', icon: '⚽', rating: playerData.football_rating });
        }
        if (playerData.basketball_rating) {
            skills.push({ sport: 'Basketball', icon: '🏀', rating: playerData.basketball_rating });
        }

        if (skills.length > 0) {
            skills.forEach(skill => {
                const skillItem = document.createElement('div');
                skillItem.className = 'skill-item';

                skillItem.innerHTML = `
                    <div class="skill-header">
                        <span class="skill-icon">${skill.icon}</span>
                        <span class="skill-name">${skill.sport}</span>
                    </div>
                    <div class="skill-rating">
                        <div class="rating-bar">
                            <div class="rating-fill" style="width: ${skill.rating * 10}%"></div>
                        </div>
                        <span class="rating-value">${skill.rating}</span>
                    </div>
                `;

                skillsGrid.appendChild(skillItem);
            });
        } else {
            // Show default empty state if no skills exist
            skillsGrid.innerHTML = '<p style="color: #64748b; padding: 1rem;">No sports skills data available.</p>';
        }
    } catch (error) {
        console.error('Error loading skills:', error);
    }
}

// Load and display recent activities
function loadActivities() {
    const activityList = document.getElementById('activityList');
    activityList.innerHTML = '';

    // Show no activity message instead of dummy data
    activityList.innerHTML = `
        <div style="text-align: center; padding: 2rem; color: #64748b;">
            <i class="fas fa-clock" style="font-size: 2rem; margin-bottom: 1rem; opacity: 0.5;"></i>
            <p>No recent activity to display</p>
            <small style="opacity: 0.7;">Your activity will appear here as you participate in events and auctions</small>
        </div>
    `;
}

// Setup event listeners for action buttons
function setupEventListeners() {
    // These functions would be implemented based on requirements
    window.updateProfile = function () {
        adminLogActivity('Player Profile Update', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
        showModal('Update Profile', 'Profile update functionality would be implemented here.');
    };

    window.viewEvents = function () {
        adminLogActivity('Player View Events', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
        showModal('View Events', 'Events listing functionality would be implemented here.');
    };

    window.viewAnalytics = function () {
        adminLogActivity('Player View Analytics', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
        showModal('View Analytics', 'Analytics dashboard functionality would be implemented here.');
    };

    // Edit skills function
    window.editSkills = function () {
        adminLogActivity('Player Edit Skills', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
        
        const modalHtml = `
            <h2>Edit Sports Skills & Ratings</h2>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Cricket Rating (1-10)</label>
                <input type="number" id="cricketRating" min="1" max="10" value="${document.querySelector('#skillsGrid .skill-item:nth-child(1) .rating-value')?.textContent || 0}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Football Rating (1-10)</label>
                <input type="number" id="footballRating" min="1" max="10" value="${document.querySelector('#skillsGrid .skill-item:nth-child(2) .rating-value')?.textContent || 0}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Basketball Rating (1-10)</label>
                <input type="number" id="basketballRating" min="1" max="10" value="${document.querySelector('#skillsGrid .skill-item:nth-child(3) .rating-value')?.textContent || 0}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="display: flex; gap: 1rem; margin-top: 1.5rem;">
                <button onclick="saveSkills()" style="flex: 1; padding: 0.5rem; background: #f97316; color: white; border: none; border-radius: 0.25rem; cursor: pointer;">Save</button>
                <button onclick="closeModal()" style="flex: 1; padding: 0.5rem; background: #334155; color: white; border: none; border-radius: 0.25rem; cursor: pointer;">Cancel</button>
            </div>
        `;
        
        showEditModal('Edit Sports Skills & Ratings', modalHtml);
    };

    // Edit performance metrics function
    window.editPerformanceMetrics = function () {
        adminLogActivity('Player Edit Performance Metrics', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
        
        const modalHtml = `
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Total Events Participated</label>
                <input type="number" id="totalEventsInput" min="0" value="${document.getElementById('totalEvents').textContent}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Auction Success Rate (%)</label>
                <input type="number" id="successRateInput" min="0" max="100" value="${parseInt(document.getElementById('successRate').textContent)}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Average Bid Amount (₹)</label>
                <input type="number" id="avgBidInput" min="0" value="${parseInt(document.getElementById('avgBid').textContent.replace(/[₹,]/g, ''))}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Highest Winning Bid (₹)</label>
                <input type="number" id="highestBidInput" min="0" value="${parseInt(document.getElementById('highestBid').textContent.replace(/[₹,]/g, ''))}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Teams Interested</label>
                <input type="number" id="teamsInterestedInput" min="0" value="${document.getElementById('teamsInterested').textContent}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Profile Views</label>
                <input type="number" id="profileViewsInput" min="0" value="${document.getElementById('profileViews').textContent}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="display: flex; gap: 1rem; margin-top: 1.5rem;">
                <button onclick="savePerformanceMetrics()" style="flex: 1; padding: 0.5rem; background: #f97316; color: white; border: none; border-radius: 0.25rem; cursor: pointer;">Save</button>
                <button onclick="closeModal()" style="flex: 1; padding: 0.5rem; background: #334155; color: white; border: none; border-radius: 0.25rem; cursor: pointer;">Cancel</button>
            </div>
        `;
        
        showEditModal('Edit Performance Metrics', modalHtml);
    };

    // Edit achievements function
    window.editAchievements = function () {
        adminLogActivity('Player Edit Achievements', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
        
        const modalHtml = `
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Tournaments Won</label>
                <input type="number" id="tournamentsWonInput" min="0" value="${document.getElementById('tournamentsWon').textContent}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">MVP Awards</label>
                <input type="number" id="mvpAwardsInput" min="0" value="${document.getElementById('mvpAwards').textContent}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Best Player Awards</label>
                <input type="number" id="bestPlayerAwardsInput" min="0" value="${document.getElementById('bestPlayerAwards').textContent}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: flex; align-items: center; gap: 0.5rem; color: #94a3b8;">
                    <input type="checkbox" id="stateChampionInput" ${document.getElementById('stateChampion').textContent === 'Yes' ? 'checked' : ''}>
                    State Level Champion
                </label>
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: flex; align-items: center; gap: 0.5rem; color: #94a3b8;">
                    <input type="checkbox" id="internationalExpInput" ${document.getElementById('internationalExp').textContent === 'Yes' ? 'checked' : ''}>
                    International Experience
                </label>
            </div>
            <div style="margin-bottom: 1rem;">
                <label style="display: block; margin-bottom: 0.5rem; color: #94a3b8;">Professional Contracts</label>
                <input type="number" id="proContractsInput" min="0" value="${document.getElementById('proContracts').textContent}" 
                    style="width: 100%; padding: 0.5rem; background: #1e293b; border: 1px solid #334155; border-radius: 0.25rem; color: white;">
            </div>
            <div style="display: flex; gap: 1rem; margin-top: 1.5rem;">
                <button onclick="saveAchievements()" style="flex: 1; padding: 0.5rem; background: #f97316; color: white; border: none; border-radius: 0.25rem; cursor: pointer;">Save</button>
                <button onclick="closeModal()" style="flex: 1; padding: 0.5rem; background: #334155; color: white; border: none; border-radius: 0.25rem; cursor: pointer;">Cancel</button>
            </div>
        `;
        
        showEditModal('Edit Achievements', modalHtml);
    };
}

// Utility function to format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric'
    });
}

// Show edit modal with custom content
function showEditModal(title, contentHtml) {
    let modal = document.querySelector('.edit-modal-overlay');
    if (!modal) {
        modal = document.createElement('div');
        modal.className = 'edit-modal-overlay';
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

        const modalContent = document.createElement('div');
        modalContent.className = 'edit-modal-content';
        modalContent.style.backgroundColor = '#1e293b';
        modalContent.style.padding = '2rem';
        modalContent.style.borderRadius = '0.5rem';
        modalContent.style.maxWidth = '500px';
        modalContent.style.width = '90%';
        modalContent.style.position = 'relative';

        modal.appendChild(modalContent);
        document.body.appendChild(modal);
    }

    const modalContent = modal.querySelector('.edit-modal-content');
    modalContent.innerHTML = contentHtml;

    modal.style.display = 'flex';

    modal.onclick = function (event) {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    };

    return modal;
}

// Close modal function
window.closeModal = function() {
    const modal = document.querySelector('.edit-modal-overlay');
    if (modal) {
        modal.style.display = 'none';
    }
};

// Save skills function
window.saveSkills = async function() {
    const cricketRating = parseInt(document.getElementById('cricketRating').value);
    const footballRating = parseInt(document.getElementById('footballRating').value);
    const basketballRating = parseInt(document.getElementById('basketballRating').value);

    try {
        const response = await fetch('/api/player/skills', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                cricket_rating: cricketRating,
                football_rating: footballRating,
                basketball_rating: basketballRating
            })
        });

        if (response.ok) {
            closeModal();
            loadSkills();
            adminLogActivity('Player Skills Updated', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
            showModal('Success', 'Skills updated successfully!');
        } else {
            showModal('Error', 'Failed to update skills. Please try again.');
        }
    } catch (error) {
        console.error('Error saving skills:', error);
        showModal('Error', 'Failed to update skills. Please try again.');
    }
};

// Save performance metrics function
window.savePerformanceMetrics = async function() {
    const data = {
        total_events_participated: parseInt(document.getElementById('totalEventsInput').value),
        auction_success_rate: parseInt(document.getElementById('successRateInput').value),
        average_bid_amount: parseFloat(document.getElementById('avgBidInput').value),
        highest_winning_bid: parseFloat(document.getElementById('highestBidInput').value),
        teams_interested: parseInt(document.getElementById('teamsInterestedInput').value),
        profile_views: parseInt(document.getElementById('profileViewsInput').value)
    };

    try {
        const response = await fetch('/api/player/performance-metrics', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            closeModal();
            loadPlayerData();
            adminLogActivity('Player Performance Metrics Updated', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
            showModal('Success', 'Performance metrics updated successfully!');
        } else {
            showModal('Error', 'Failed to update performance metrics. Please try again.');
        }
    } catch (error) {
        console.error('Error saving performance metrics:', error);
        showModal('Error', 'Failed to update performance metrics. Please try again.');
    }
};

// Save achievements function
window.saveAchievements = async function() {
    const data = {
        tournaments_won: parseInt(document.getElementById('tournamentsWonInput').value),
        mvp_awards: parseInt(document.getElementById('mvpAwardsInput').value),
        best_player_awards: parseInt(document.getElementById('bestPlayerAwardsInput').value),
        state_level_champion: document.getElementById('stateChampionInput').checked,
        international_experience: document.getElementById('internationalExpInput').checked,
        professional_contracts: parseInt(document.getElementById('proContractsInput').value)
    };

    try {
        const response = await fetch('/api/player/achievements', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            closeModal();
            loadPlayerData();
            adminLogActivity('Player Achievements Updated', `Username: ${sessionStorage.getItem('username') || 'Unknown'}`, 'player');
            showModal('Success', 'Achievements updated successfully!');
        } else {
            showModal('Error', 'Failed to update achievements. Please try again.');
        }
    } catch (error) {
        console.error('Error saving achievements:', error);
        showModal('Error', 'Failed to update achievements. Please try again.');
    }
};

// Show modal function for player dashboard
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
    const modalContent = modal.querySelector('div') || modal;
    let titleElement = modal.querySelector('h2');
    let messageElement = modal.querySelector('div:nth-child(2)');

    if (!titleElement) {
        titleElement = document.createElement('h2');
        titleElement.style.color = '#ffffff';
        titleElement.style.marginTop = '0';
        titleElement.style.marginBottom = '1rem';
        modalContent.insertBefore(titleElement, modalContent.firstChild);
    }

    if (!messageElement) {
        messageElement = document.createElement('div');
        messageElement.style.color = '#94a3b8';
        messageElement.style.lineHeight = '1.6';
        messageElement.style.marginBottom = '1.5rem';
        const okButton = modal.querySelector('button');
        if (okButton) {
            modalContent.insertBefore(messageElement, okButton);
        } else {
            modalContent.appendChild(messageElement);
        }
    }

    // Set the content
    titleElement.textContent = title;
    messageElement.innerHTML = message;

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

// Logout function
async function logout() {
    const userStr = localStorage.getItem('user');
    const user = userStr ? JSON.parse(userStr) : null;
    const username = user ? user.username : 'Unknown';

    // Log the logout action
    adminLogActivity('Player Logout', `Username: ${username}`, 'player');

    try {
        await fetch('/api/logout', { method: 'POST' });
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
    localStorage.removeItem(`player_${username}`);
    
    window.location.replace('/');
}
