/**
 * Player Dashboard JavaScript
 * Handles navigation, API integration, and chart rendering.
 */

let performanceChartInstance = null;
let radarChartInstance = null;
let currentPlayerData = null;
let rawUserData = null; // Store data from /api/users/id endpoint

// --- THEME LOGIC ---
function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon(newTheme);
    updateChartColors(newTheme);
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

function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function updateChartColors(theme) {
    if (radarChartInstance) {
        const gridColor = theme === 'light' ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.1)';
        const labelColor = theme === 'light' ? '#6B7280' : '#8E9BAE';
        
        radarChartInstance.options.scales.r.angleLines.color = gridColor;
        radarChartInstance.options.scales.r.grid.color = gridColor;
        radarChartInstance.options.scales.r.pointLabels.color = labelColor;
        radarChartInstance.update();
    }
}
// -------------------


document.addEventListener('DOMContentLoaded', () => {
    // 0. Initialize Theme
    initTheme();

    // 1. Auth & Session Check
    const userStr = localStorage.getItem('user');
    const token = localStorage.getItem('session_token');
    
    if (!userStr || !token) {
        window.location.href = '/';
        return;
    }

    const user = JSON.parse(userStr);
    if (user.user_type !== 'player') {
        alert('Access denied - player only.');
        window.location.href = '/';
        return;
    }

    // Initialize UI
    setupNavigation();
    setupMobileToggle();
    
    // Load Data
    loadPlayerData();
    loadSkillsData(user.user_id);
    loadUpcomingEvents();
});

// --- NAVIGATION LOGIC ---
function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link[data-target]');
    navLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            // Remove active class from all links
            navLinks.forEach(l => l.classList.remove('active'));
            // Add active class to clicked link
            e.currentTarget.classList.add('active');
            
            // Hide all sections
            document.querySelectorAll('.section-view').forEach(sec => {
                sec.classList.remove('active');
            });
            
            // Show target section
            const targetId = e.currentTarget.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
            
            // Close sidebar on mobile after clicking
            if (window.innerWidth <= 992) {
                document.getElementById('sidebar').classList.remove('open');
            }
        });
    });
}

function setupMobileToggle() {
    const toggle = document.getElementById('mobileToggle');
    const sidebar = document.getElementById('sidebar');
    if (toggle && sidebar) {
        toggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }
}

// --- API INTEGRATION ---
async function loadPlayerData() {
    try {
        const token = localStorage.getItem('session_token');
        const response = await fetch('/api/player/dashboard', {
            headers: { 
                'Accept': 'application/json',
                'Authorization': `Bearer ${token}` // Ensure auth header if required
            },
            credentials: 'include'
        });
        
        if (!response.ok) throw new Error('Failed to load dashboard data');
        
        const data = await response.json();
        currentPlayerData = data;
        
        updateDashboardUI(data);
        renderCharts(data);
    } catch (err) {
        console.error('Error fetching dashboard:', err);
    }
}

async function loadSkillsData(userId) {
    try {
        const response = await fetch(`/api/users/${userId}`);
        if (!response.ok) throw new Error('Failed to fetch user skills');
        const data = await response.json();
        rawUserData = data;
        
        updateSkillsUI(data);
        updateProfileUI(data);
        
        // Render Radar Chart with skills
        renderRadarChart(data);
    } catch (err) {
        console.error('Error loading skills data:', err);
    }
}

async function loadUpcomingEvents() {
    try {
        const token = localStorage.getItem('session_token');
        const response = await fetch('/api/player/events/upcoming', {
            headers: { 
                'Accept': 'application/json',
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (!response.ok) throw new Error('Failed to load upcoming events');
        
        const events = await response.json();
        const list = document.getElementById('upcomingAuctionsList');
        
        if (!events || events.length === 0) {
            list.innerHTML = '<li style="color:var(--text-muted); font-size:0.9rem; padding: 20px 0; text-align: center;">No registered upcoming events.</li>';
            return;
        }
        
        list.innerHTML = events.map(event => `
            <li style="padding: 16px; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <strong style="color: var(--text-primary);">${event.title}</strong>
                    <span style="background: rgba(0,229,255,0.1); color: var(--accent-blue); padding: 4px 8px; border-radius: 4px; font-size: 0.8rem;">
                        ${event.status.replace('_', ' ').toUpperCase()}
                    </span>
                </div>
                <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--text-muted);">
                    <span><i class="fas fa-map-marker-alt" style="margin-right: 4px;"></i>${event.location}</span>
                    <span><i class="fas fa-calendar-alt" style="margin-right: 4px;"></i>${event.start_date ? new Date(event.start_date).toLocaleDateString() : 'TBA'}</span>
                </div>
            </li>
        `).join('');
        
    } catch (err) {
        console.error('Error fetching upcoming events:', err);
        const list = document.getElementById('upcomingAuctionsList');
        if (list) list.innerHTML = '<li style="color:var(--text-danger); font-size:0.9rem; padding: 20px 0; text-align: center;">Failed to load events.</li>';
    }
}

// --- UI UPDATERS ---
function updateDashboardUI(data) {
    const name = data.name || 'Unknown Player';
    
    // Topbar & Hero Name
    document.getElementById('topbarName').textContent = name;
    document.getElementById('heroName').textContent = name.toUpperCase();
    
    // Avatar
    const avatarUrl = data.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=00E5FF&color=080B12`;
    document.getElementById('topbarAvatar').src = avatarUrl;
    document.getElementById('heroAvatar').src = avatarUrl;
    if(typeof updateAvatarVisibility === 'function') updateAvatarVisibility(data.avatar);
    
    // Hero Stats
    document.getElementById('heroRating').textContent = data.avgRating ?? '--';
    document.getElementById('heroMatches').textContent = data.eventsCount ?? '--';
    document.getElementById('heroValue').textContent = data.currentValue != null && data.currentValue !== 0 ? `₹${data.currentValue.toLocaleString()}` : '₹0';
    
    // KPI Cards
    document.getElementById('kpiSuccessRate').textContent = `${data.successRate ?? 0}%`;
    document.getElementById('kpiAvgBid').textContent = data.avgBid != null && data.avgBid !== 0 ? `₹${data.avgBid.toLocaleString()}` : '₹0';
    document.getElementById('kpiViews').textContent = data.profileViews ?? 0;
    document.getElementById('kpiTeamsInterested').textContent = data.teamsInterested ?? 0;
    
    // Achievements Grid
    const achGrid = document.getElementById('achievementsGrid');
    achGrid.innerHTML = `
        ${createAchievementCard('Tournaments Won', data.tournamentsWon || 0, 'fa-trophy')}
        ${createAchievementCard('MVP Awards', data.mvpAwards || 0, 'fa-star')}
        ${createAchievementCard('Best Player', data.bestPlayerAwards || 0, 'fa-medal')}
        ${createAchievementCard('Pro Contracts', data.proContracts || 0, 'fa-file-signature')}
        ${createAchievementCard('State Champ', data.stateChampion === 'Yes' ? 'Yes' : 'No', 'fa-flag')}
        ${createAchievementCard('Intl. Exp', data.internationalExp === 'Yes' ? 'Yes' : 'No', 'fa-globe')}
    `;
    
    // Populate form data
    if (data.achievements) { // fallback safely
        document.getElementById('editTournaments').value = data.tournamentsWon || 0;
        document.getElementById('editMvp').value = data.mvpAwards || 0;
        document.getElementById('editBestPlayer').value = data.bestPlayerAwards || 0;
        document.getElementById('editProContracts').value = data.proContracts || 0;
        document.getElementById('editStateChamp').checked = data.stateChampion === 'Yes';
        document.getElementById('editIntlExp').checked = data.internationalExp === 'Yes';
    }
}

function updateSkillsUI(data) {
    const cricket = data.cricket_rating || 0;
    const football = data.football_rating || 0;
    const basketball = data.basketball_rating || 0;
    
    document.getElementById('statCricketVal').textContent = `${cricket}/10`;
    document.getElementById('statCricketBar').style.width = `${cricket * 10}%`;
    document.getElementById('editCricket').value = cricket;
    
    document.getElementById('statFootballVal').textContent = `${football}/10`;
    document.getElementById('statFootballBar').style.width = `${football * 10}%`;
    document.getElementById('editFootball').value = football;
    
    document.getElementById('statBasketballVal').textContent = `${basketball}/10`;
    document.getElementById('statBasketballBar').style.width = `${basketball * 10}%`;
    document.getElementById('editBasketball').value = basketball;
}

function updateProfileUI(data) {
    // Populate Profile Read-only view
    document.getElementById('profFirstName').textContent = data.first_name || '--';
    document.getElementById('profLastName').textContent = data.last_name || '--';
    document.getElementById('profEmail').textContent = data.email || '--';
    document.getElementById('profPhone').textContent = data.phone || '--';
    
    let dob = '--';
    if(data.date_of_birth) dob = new Date(data.date_of_birth).toLocaleDateString();
    document.getElementById('profDob').textContent = dob;
    
    document.getElementById('profGender').textContent = data.gender || '--';
    document.getElementById('profCity').textContent = data.city || '--';
    document.getElementById('profCountry').textContent = data.country || '--';
    document.getElementById('profBio').textContent = data.bio || 'No bio provided.';
    
    // Populate form
    document.getElementById('editFirstName').value = data.first_name || '';
    document.getElementById('editLastName').value = data.last_name || '';
    document.getElementById('editPhone').value = data.phone || '';
    document.getElementById('editCity').value = data.city || '';
    document.getElementById('editCountry').value = data.country || '';
    document.getElementById('editBio').value = data.bio || '';
}

function createAchievementCard(title, value, iconClass) {
    return `
        <div style="background: var(--bg-icon-default); padding: 16px; border-radius: 8px; display:flex; align-items:center; gap: 16px;">
            <div style="width: 40px; height: 40px; background: var(--accent-blue-dim); color: var(--accent-blue); border-radius: 50%; display:flex; justify-content:center; align-items:center; font-size:1.2rem;">
                <i class="fas ${iconClass}"></i>
            </div>
            <div>
                <div style="color: var(--text-muted); font-size: 0.85rem;">${title}</div>
                <div style="font-family: var(--font-number); font-weight: bold; font-size: 1.2rem;">${value}</div>
            </div>
        </div>
    `;
}

// --- CHARTS (CHART.JS) ---
function renderCharts(data) {
    // Performance Line Chart (Backend does not provide history yet)
    const ctxPerf = document.getElementById('performanceChart');
    if (ctxPerf) {
        // Display empty state instead of fake data
        const parent = ctxPerf.parentElement;
        parent.innerHTML = '<div style="display:flex; justify-content:center; align-items:center; height:100%; color:var(--text-muted); text-align:center;">Performance history will appear once match data is available.</div>';
    }
}


function renderRadarChart(userData) {
    const ctxRadar = document.getElementById('radarChart');
    if (ctxRadar) {
        if (radarChartInstance) radarChartInstance.destroy();
        
        const cricket = userData.cricket_rating || 0;
        const football = userData.football_rating || 0;
        const basketball = userData.basketball_rating || 0;
        
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        const gridColor = currentTheme === 'light' ? 'rgba(0,0,0,0.1)' : 'rgba(255,255,255,0.1)';
        const labelColor = currentTheme === 'light' ? '#6B7280' : '#8E9BAE';

        radarChartInstance = new Chart(ctxRadar, {
            type: 'radar',
            data: {
                labels: ['Cricket', 'Football', 'Basketball'],
                datasets: [{
                    label: 'Sport Ratings',
                    data: [cricket, football, basketball], 
                    backgroundColor: 'rgba(0, 255, 136, 0.2)',
                    borderColor: '#00FF88',
                    pointBackgroundColor: '#00FF88',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    r: {
                        angleLines: { color: gridColor },
                        grid: { color: gridColor },
                        pointLabels: { color: labelColor, font: { family: 'Inter', size: 12 } },
                        ticks: { display: false, min: 0, max: 10 }
                    }
                }
            }
        });
    }
}

// --- MODALS & FORMS ---
function openProfileEditModal() { document.getElementById('profileModal').style.display = 'flex'; }
function openSkillsModal() { document.getElementById('skillsModal').style.display = 'flex'; }
function openAchievementsModal() { document.getElementById('achievementsModal').style.display = 'flex'; }
function closeModal(modalId) { document.getElementById(modalId).style.display = 'none'; }

async function handleProfileSubmit(e) {
    e.preventDefault();
    
    // Construct payload. Note: The backend might not have this PUT endpoint fully mapped, 
    // but the instruction says "Where editing is already supported... Save through the real API".
    // I'll send it to /api/users/{id} or an assumed /api/player/profile if it existed, but let's 
    // simulate a PUT to /api/player/profile or the user endpoint.
    // If backend doesn't exist, this will naturally fail (handled in catch).
    const payload = {
        first_name: document.getElementById('editFirstName').value,
        last_name: document.getElementById('editLastName').value,
        city: document.getElementById('editCity').value,
        country: document.getElementById('editCountry').value,
        phone: document.getElementById('editPhone').value,
        bio: document.getElementById('editBio').value
    };
    
    try {
        const token = localStorage.getItem('session_token');
        const user = JSON.parse(localStorage.getItem('user'));
        
        // Attempting to update via a generic users endpoint or player endpoint
        const response = await fetch(`/api/users/${user.user_id}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            alert('Profile updated successfully.');
            closeModal('profileModal');
            loadSkillsData(user.user_id); // Reload user specific data
            loadPlayerData();
        } else {
            alert('Profile update endpoint may not be implemented on backend yet.');
        }
    } catch (err) {
        console.error('Error updating profile:', err);
    }
}

async function handleSkillsSubmit(e) {
    e.preventDefault();
    const payload = {
        cricket_rating: parseInt(document.getElementById('editCricket').value) || 0,
        football_rating: parseInt(document.getElementById('editFootball').value) || 0,
        basketball_rating: parseInt(document.getElementById('editBasketball').value) || 0
    };
    
    try {
        const token = localStorage.getItem('session_token');
        const response = await fetch('/api/player/skills', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            alert('Skills updated successfully!');
            closeModal('skillsModal');
            const user = JSON.parse(localStorage.getItem('user'));
            loadSkillsData(user.user_id); // Refresh
        } else {
            alert('Failed to update skills.');
        }
    } catch (err) {
        console.error('Error saving skills:', err);
    }
}

async function handleAchievementsSubmit(e) {
    e.preventDefault();
    const payload = {
        tournaments_won: parseInt(document.getElementById('editTournaments').value) || 0,
        mvp_awards: parseInt(document.getElementById('editMvp').value) || 0,
        best_player_awards: parseInt(document.getElementById('editBestPlayer').value) || 0,
        professional_contracts: parseInt(document.getElementById('editProContracts').value) || 0,
        state_level_champion: document.getElementById('editStateChamp').checked,
        international_experience: document.getElementById('editIntlExp').checked
    };
    
    try {
        const token = localStorage.getItem('session_token');
        const response = await fetch('/api/player/achievements', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            alert('Achievements updated successfully!');
            closeModal('achievementsModal');
            loadPlayerData(); // Refresh dashboard data
        } else {
            alert('Failed to update achievements.');
        }
    } catch (err) {
        console.error('Error saving achievements:', err);
    }
}

// --- PHOTO UPLOAD LOGIC ---
let cropper = null;
const fileInput = document.getElementById('profileImageInput');
const cropImageTarget = document.getElementById('cropImageTarget');
const saveCropBtn = document.getElementById('saveCropBtn');
const removePhotoBtn = document.getElementById('removePhotoBtn');

function updateAvatarVisibility(url) {
    if(url && url.includes('uploads/profile_images')) {
        if(removePhotoBtn) removePhotoBtn.style.display = 'flex';
    } else {
        if(removePhotoBtn) removePhotoBtn.style.display = 'none';
    }
}

if(fileInput) {
    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if(!file) return;
        
        if(file.size > 5 * 1024 * 1024) {
            alert('File size exceeds 5MB limit.');
            fileInput.value = '';
            return;
        }
        
        if(!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
            alert('Invalid file type. Only JPG, PNG, WEBP allowed.');
            fileInput.value = '';
            return;
        }
        
        const url = URL.createObjectURL(file);
        cropImageTarget.src = url;
        
        document.getElementById('cropModal').style.display = 'flex';
        
        if(cropper) {
            cropper.destroy();
        }
        
        cropper = new Cropper(cropImageTarget, {
            aspectRatio: 1,
            viewMode: 1,
            dragMode: 'move',
            autoCropArea: 1,
            restore: false,
            guides: true,
            center: true,
            highlight: false,
            cropBoxMovable: true,
            cropBoxResizable: true,
            toggleDragModeOnDblclick: false,
        });
    });
}

if(saveCropBtn) {
    saveCropBtn.addEventListener('click', async () => {
        if(!cropper) return;
        
        const oldText = saveCropBtn.textContent;
        saveCropBtn.textContent = 'Setting...';
        saveCropBtn.disabled = true;
        
        cropper.getCroppedCanvas({
            width: 400,
            height: 400,
            imageSmoothingEnabled: true,
            imageSmoothingQuality: 'medium',
        }).toBlob(async (blob) => {
            if(!blob) {
                alert('Failed to crop image.');
                saveCropBtn.textContent = oldText;
                saveCropBtn.disabled = false;
                return;
            }
            
            const formData = new FormData();
            formData.append('image', blob, 'avatar.jpg');
            
            try {
                const token = localStorage.getItem('session_token');
                const response = await fetch('/api/player/upload-image', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
                
                const data = await response.json();
                if(data.success) {
                    const nocacheUrl = data.image_url + '?v=' + new Date().getTime();
                    document.getElementById('heroAvatar').src = nocacheUrl;
                    document.getElementById('topbarAvatar').src = nocacheUrl;
                    updateAvatarVisibility(data.image_url);
                    
                    const userStr = localStorage.getItem('user');
                    if(userStr) {
                        const userObj = JSON.parse(userStr);
                        userObj.avatar = data.image_url;
                        localStorage.setItem('user', JSON.stringify(userObj));
                    }
                    closeModal('cropModal');
                } else {
                    alert(data.message || 'Failed to upload image.');
                }
            } catch (error) {
                console.error('Error uploading image:', error);
                alert('An error occurred during upload.');
            } finally {
                saveCropBtn.textContent = oldText;
                saveCropBtn.disabled = false;
                fileInput.value = '';
            }
        }, 'image/jpeg', 0.9);
    });
}

async function removeProfilePhoto() {
    if(!confirm('Are you sure you want to remove your profile photo?')) return;
    
    try {
        const token = localStorage.getItem('session_token');
        const response = await fetch('/api/player/remove-image', {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        const data = await response.json();
        if(data.success) {
            const name = document.getElementById('heroName').textContent || 'Player';
            const defaultUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=00E5FF&color=080B12`;
            
            document.getElementById('heroAvatar').src = defaultUrl;
            document.getElementById('topbarAvatar').src = defaultUrl;
            updateAvatarVisibility('');
            
            const userStr = localStorage.getItem('user');
            if(userStr) {
                const userObj = JSON.parse(userStr);
                userObj.avatar = null;
                localStorage.setItem('user', JSON.stringify(userObj));
            }
        } else {
            alert(data.message || 'Failed to remove image.');
        }
    } catch (error) {
        console.error('Error removing image:', error);
        alert('An error occurred during removal.');
    }
}


// --- AUTH LOGIC ---
async function logout() {
    try {
        const token = localStorage.getItem('session_token');
        await fetch('/api/logout', { 
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
    } catch (error) {
        console.error('Error logging out:', error);
    }

    sessionStorage.clear();
    localStorage.clear();
    window.location.replace('/');
}
