// live-auction.js

let socket;
let currentEventId;
let user;
let userTeamId = null;

let currentDeadline = null; // High-precision timestamp from server
let currentBidAmount = 0;
let highestBidderTeamId = null;
let currentAuctionPlayerId = null;

let teamsMap = {}; // Maps team_id to team data

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Verify Auth
    const userStr = localStorage.getItem('user');
    if (!userStr) {
        window.location.href = '/';
        return;
    }
    user = JSON.parse(userStr);
    
    // Determine user's team if they are an owner
    if (user.user_type === 'team_owner' && user.team && user.team.team_id) {
        userTeamId = user.team.team_id;
    }

    // Adjust UI based on Role
    if (user.user_type === 'admin' || user.user_type === 'superadmin') {
        document.getElementById('adminPanel').classList.add('active');
    }

    // 2. Get Event ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    currentEventId = urlParams.get('id');
    if (!currentEventId) {
        alert("No event ID provided");
        window.location.href = '/';
        return;
    }

    // 3. Load Auction Data
    await loadAuctionData();

    // 4. Initialize Socket
    initSocket();

    // 5. Start Render Loop
    requestAnimationFrame(renderTimer);
});

async function loadAuctionData() {
    try {
        const response = await fetch(`/api/events/${currentEventId}/auction`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`
            }
        });
        const data = await response.json();
        
        if (data.success) {
            // Update Event Header
            if (data.event) {
                const headerEl = document.getElementById('eventNameHeader');
                if(headerEl) headerEl.textContent = `Live Auction: ${data.event.name}`;
            }

            // Render Teams
            if (data.teams) {
                renderTeams(data.teams);
            }
            
            // Render Players Queue
            if (data.players) {
                renderPlayers(data.players);
            }

            // Update Current Auction State
            updateAuctionUI(data);
        } else {
            console.error("Failed to load auction data", data);
            showToast("Failed to load auction data.", true);
        }
    } catch (e) {
        console.error("Failed to fetch auction data", e);
        showToast("Error connecting to server.", true);
    }
}

function renderTeams(teams) {
    const container = document.getElementById('teamsContainer');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (!teams || teams.length === 0) {
        container.innerHTML = `<div class="empty-state">No teams have registered for this event yet.</div>`;
        return;
    }
    
    teams.forEach((team) => {
        teamsMap[team.team_id] = team;
        
        const card = document.createElement('div');
        card.className = 'team-card';
        card.style.position = 'relative';
        card.id = `team-slot-${team.team_id}`;
        
        const isMyTeam = (team.team_id === userTeamId);
        
        card.innerHTML = `
            <div style="position: absolute; top: 10px; left: 15px; font-weight: bold; color: rgba(255,255,255,0.4); font-size: 1.2rem;">#${team.order}</div>
            <div class="team-logo">${team.team_name.charAt(0).toUpperCase()}</div>
            <div class="team-name">${team.team_name}</div>
            <div class="team-stats">
                <span>Purse: ₹${team.purse !== undefined ? team.purse.toLocaleString() : '--'}</span>
                <span>Players: ${team.players_count || 0} / ${team.max_players || 15}</span>
            </div>
            
            ${isMyTeam ? `
            <div class="bid-action-area" style="display:block;">
                <button id="btnBid" class="btn-bid" onclick="placeBid()">BID</button>
            </div>
            ` : ''}
        `;
        container.appendChild(card);
        team.elementId = card.id;
    });
}

function renderPlayers(players) {
    const container = document.getElementById('playerQueueContainer');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (!players || players.length === 0) {
        container.innerHTML = `<div class="empty-state">No players have registered for this event yet.</div>`;
        return;
    }
    
    players.forEach(player => {
        const item = document.createElement('div');
        item.className = 'queue-item';
        item.id = `queue-player-${player.id}`;
        
        let statusHtml = '';
        if (player.status === 'SOLD') {
            statusHtml = `
                <div class="flex flex-col items-end">
                    <div class="queue-item-status status-sold">SOLD</div>
                    <div class="text-xs font-bold text-slate-300 mt-1">₹${player.sold_amount ? player.sold_amount.toLocaleString() : 0}</div>
                    <div class="text-[10px] text-slate-400 mt-0.5">${player.sold_to || ''}</div>
                </div>
            `;
        } else {
            statusHtml = `<div class="queue-item-status status-upcoming">UPCOMING</div>`;
        }
        
        item.innerHTML = `
            <img src="${player.photo}" alt="${player.name}" onerror="this.src='/static/images/default-avatar.png'">
            <div class="queue-item-info">
                <div class="queue-item-name" title="${player.name}">${player.name}</div>
                <div class="queue-item-role">${player.role} • ${player.category}</div>
                <div class="queue-item-price">Base: ₹${player.basePrice.toLocaleString()}</div>
            </div>
            ${statusHtml}
        `;
        container.appendChild(item);
    });
}

function initSocket() {
    socket = io({ transports: ['polling', 'websocket'], upgrade: true });

    socket.on('connect', () => {
        console.log('Connected to auction server');
        
        const badge = document.getElementById('auctionStatusBadge');
        if(badge) {
            badge.className = 'status-badge';
            badge.innerHTML = '<i class="fas fa-circle" style="font-size: 8px;"></i> LIVE';
        }

        socket.emit('join_lobby', {
            auction_id: currentEventId,
            team_id: userTeamId || 'viewer'
        });
    });
    
    socket.on('disconnect', () => {
        const badge = document.getElementById('auctionStatusBadge');
        if(badge) {
            badge.className = 'status-badge disconnected';
            badge.innerHTML = '<i class="fas fa-circle" style="font-size: 8px;"></i> DISCONNECTED';
        }
    });

    socket.on('auction_update', (data) => {
        console.log("Auction Update:", data);
        updateAuctionUI(data);
    });

    socket.on('bid_placed', (data) => {
        console.log("Bid Placed:", data);
        
        // Flash the team card
        if (teamsMap[data.team_id] && teamsMap[data.team_id].elementId) {
            const el = document.getElementById(teamsMap[data.team_id].elementId);
            el.classList.remove('flash');
            void el.offsetWidth; // trigger reflow
            el.classList.add('flash');
        }
        
        // Update bid state
        if (data.bid_deadline) {
            currentDeadline = new Date(data.bid_deadline).getTime();
        }
        currentBidAmount = data.amount || currentBidAmount;
        highestBidderTeamId = data.team_id;
        
        document.getElementById('currentBid').textContent = `₹${currentBidAmount.toLocaleString()}`;
        
        const teamName = teamsMap[data.team_id] ? teamsMap[data.team_id].team_name : 'Team ' + data.team_id;
        document.getElementById('bidLeader').textContent = `Highest Bidder: ${teamName}`;
        
        updateBidButtons();
        highlightLeader();
        showToast(`Bid placed: ₹${currentBidAmount.toLocaleString()} by ${teamName}`);
    });
    
    socket.on('player_sold', (data) => {
        // Find player in queue and mark as sold
        if (data.player_id) {
            const queueItem = document.getElementById(`queue-player-${data.player_id}`);
            if (queueItem) {
                const teamName = teamsMap[data.team_id] ? teamsMap[data.team_id].team_name : 'Unknown Team';
                const statusDiv = queueItem.querySelector('.queue-item-status');
                if (statusDiv) {
                    statusDiv.outerHTML = `
                        <div class="flex flex-col items-end">
                            <div class="queue-item-status status-sold">SOLD</div>
                            <div class="text-xs font-bold text-slate-300 mt-1">₹${data.amount ? data.amount.toLocaleString() : 0}</div>
                            <div class="text-[10px] text-slate-400 mt-0.5">${teamName}</div>
                        </div>
                    `;
                }
                queueItem.classList.remove('active');
            }
        }
        showToast(data.message || `Player sold for ₹${data.amount}`);
    });
    
    socket.on('player_unsold', (data) => {
        if (data.player_id) {
            const queueItem = document.getElementById(`queue-player-${data.player_id}`);
            if (queueItem) {
                const statusDiv = queueItem.querySelector('.queue-item-status');
                if (statusDiv) {
                    statusDiv.outerHTML = `<div class="queue-item-status status-upcoming" style="color: #ef4444;">UNSOLD</div>`;
                }
                queueItem.classList.remove('active');
            }
        }
        showToast(data.message || "Player went unsold.");
    });

    socket.on('error', (err) => {
        console.error("Socket error:", err);
        showToast(err.msg || err.error || "Error", true);
    });
}

let pausedTimeLeft = null;

function updateAuctionUI(data) {
    const lobbyOverlay = document.getElementById('lobbyOverlay');
    const playerContent = document.getElementById('playerContent');
    
    // Control Buttons
    const btnStart = document.getElementById('btnStartAuction');
    const btnPause = document.getElementById('btnPauseAuction');
    const btnResume = document.getElementById('btnResumeAuction');
    const btnStop = document.getElementById('btnStopAuction');
    const btnNext = document.getElementById('btnNextPlayer');
    const btnMarkSold = document.getElementById('btnMarkSold');
    const btnMarkUnsold = document.getElementById('btnMarkUnsold');

    // Update Deadline
    if (data.bid_deadline) {
        currentDeadline = new Date(data.bid_deadline).getTime();
        pausedTimeLeft = null;
    } else if (data.paused_time_left !== undefined && data.paused_time_left !== null) {
        currentDeadline = null;
        pausedTimeLeft = data.paused_time_left;
        const display = document.getElementById('bidTimer');
        if (display) display.textContent = Math.ceil(pausedTimeLeft).toString().padStart(2, '0');
    } else {
        currentDeadline = null;
    }
    
    // Update Bid Info
    if (data.first_bidder_team_id && teamsMap[data.first_bidder_team_id]) {
        const firstTeam = teamsMap[data.first_bidder_team_id];
        const el = document.getElementById('firstBidderInfo');
        if (el) {
            el.style.display = 'block';
            document.getElementById('firstBidderTeam').textContent = `🟢 ${firstTeam.team_name}`;
        }
    } else {
        const el = document.getElementById('firstBidderInfo');
        if (el) el.style.display = 'none';
    }
    
    if (data.current_bid !== undefined) {
        currentBidAmount = data.current_bid;
        document.getElementById('currentBid').textContent = `₹${currentBidAmount.toLocaleString()}`;
    }
    
    // Update Highest Bidder if present in data
    if (data.highest_bidder && data.highest_bidder !== '-') {
        document.getElementById('bidLeader').textContent = `Highest Bidder: ${data.highest_bidder}`;
    } else if (data.highest_bidder_team_id) {
        highestBidderTeamId = data.highest_bidder_team_id;
        const teamName = teamsMap[highestBidderTeamId] ? teamsMap[highestBidderTeamId].team_name : 'Unknown';
        document.getElementById('bidLeader').textContent = `Highest Bidder: ${teamName}`;
    }

    if (data.current_player) {
        if(lobbyOverlay) lobbyOverlay.style.display = 'none';
        if(playerContent) playerContent.style.display = 'block';

        currentAuctionPlayerId = data.current_player.id;

        document.getElementById('playerName').textContent = data.current_player.name;
        document.getElementById('playerRole').textContent = `${data.current_player.role} • ${data.current_player.category}`;
        document.getElementById('playerBasePrice').textContent = `₹${data.current_player.basePrice.toLocaleString()}`;
        document.getElementById('playerAge').textContent = data.current_player.age || '--';
        document.getElementById('playerImage').src = data.current_player.photo || '/static/images/default-avatar.png';
        
        if (data.status === 'WAITING' || data.status === 'LOBBY' || data.status === 'scheduled') {
            document.getElementById('bidLeader').textContent = `Waiting for first bid...`;
            if (data.status === 'LOBBY') {
                document.getElementById('bidTimer').textContent = `--`;
            }
        }
        
        // Highlight in queue
        document.querySelectorAll('.queue-item').forEach(el => el.classList.remove('active'));
        const activeQueueItem = document.getElementById(`queue-player-${currentAuctionPlayerId}`);
        if(activeQueueItem) {
            activeQueueItem.classList.add('active');
            activeQueueItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        
    } else {
        if(lobbyOverlay) {
            lobbyOverlay.style.display = 'flex';
            const lobbyText = document.getElementById('lobbyOverlayText');
            if(lobbyText) {
                if (data.status === 'COMPLETED' || data.status === 'completed') {
                    lobbyText.textContent = "Auction Completed";
                } else {
                    lobbyText.textContent = "No player is currently being auctioned.";
                }
            }
        }
        if(playerContent) playerContent.style.display = 'none';
    }

    // Reset button visibility
    if(btnStart) btnStart.style.display = 'none';
    if(btnPause) btnPause.style.display = 'none';
    if(btnResume) btnResume.style.display = 'none';
    if(btnStop) btnStop.style.display = 'none';
    if(btnNext) btnNext.style.display = 'none';
    if(btnMarkSold) btnMarkSold.style.display = 'none';
    if(btnMarkUnsold) btnMarkUnsold.style.display = 'none';

    // State Machine Controls
    if (data.status === 'RUNNING' || data.status === 'WAITING' || data.status === 'in_progress') {
        if(btnPause) btnPause.style.display = 'inline-block';
        if(btnStop) btnStop.style.display = 'inline-block';
        if(btnMarkSold) btnMarkSold.style.display = 'inline-block';
        if(btnMarkUnsold) btnMarkUnsold.style.display = 'inline-block';
    } else if (data.status === 'LOBBY' || data.status === 'scheduled') {
        if(btnStart) btnStart.style.display = 'inline-block';
    } else if (data.status === 'PAUSED') {
        if(btnResume) btnResume.style.display = 'inline-block';
        if(btnStop) btnStop.style.display = 'inline-block';
    } else if (data.status === 'STOPPED' || data.status === 'COMPLETED' || data.status === 'completed') {
        if(btnNext) btnNext.style.display = 'inline-block';
    }

    updateBidButtons();
    highlightLeader();
}

function renderTimer() {
    const display = document.getElementById('bidTimer');
    const displayLabel = document.getElementById('bidTimerLabel');
    if (!display) return;
    
    if (currentDeadline) {
        if (displayLabel) {
            displayLabel.style.display = 'block';
            displayLabel.textContent = "Time Remaining";
        }
        
        const now = Date.now();
        const remainingMs = currentDeadline - now;
        
        if (remainingMs > 0) {
            const secs = Math.ceil(remainingMs / 1000);
            display.textContent = secs.toString().padStart(2, '0');
            
            // Stylings based on time
            if (secs <= 5) {
                display.className = 'timer-display danger';
            } else if (secs <= 10) {
                display.className = 'timer-display warning';
            } else {
                display.className = 'timer-display';
            }
        } else {
            display.textContent = 'Processing...';
            display.className = 'timer-display warning';
            if (displayLabel) displayLabel.style.display = 'none';
            // Wait passively for server to emit player_sold or player_unsold
        }
    } else if (pausedTimeLeft !== null && pausedTimeLeft !== undefined) {
        display.textContent = Math.ceil(pausedTimeLeft).toString().padStart(2, '0');
        display.className = 'timer-display warning';
        if (displayLabel) {
            displayLabel.style.display = 'block';
            displayLabel.textContent = "PAUSED";
        }
    } else {
        display.textContent = '--:--';
        display.className = 'timer-display';
        if (displayLabel) {
            displayLabel.style.display = 'block';
            displayLabel.textContent = 'Waiting for player';
        }
    }
    
    requestAnimationFrame(renderTimer);
}

function updateBidButtons() {
    const btn = document.getElementById('btnBid');
    if (!btn) return;
    
    // Determine next bid amount. In a real app, this increment comes from the server.
    const increment = 10000;
    const nextBid = (currentBidAmount || 0) + increment;
    
    btn.textContent = `BID ₹${nextBid.toLocaleString()}`;
    
    // Disable if team is already highest bidder
    if (highestBidderTeamId && highestBidderTeamId === userTeamId) {
        btn.disabled = true;
        btn.textContent = 'LEADING';
    } else {
        btn.disabled = false;
    }
}

function highlightLeader() {
    // Clear all leaders
    document.querySelectorAll('.team-card').forEach(el => el.classList.remove('is-leader'));
    
    // Add to current leader
    if (highestBidderTeamId && teamsMap[highestBidderTeamId]) {
        const elId = teamsMap[highestBidderTeamId].elementId;
        if (elId) {
            document.getElementById(elId).classList.add('is-leader');
        }
    }
}

async function placeBid() {
    if (!currentEventId || !userTeamId) return;
    
    const increment = 10000;
    const amount = (currentBidAmount || 0) + increment; 
    
    try {
        const response = await fetch(`/api/events/${currentEventId}/auction/bid`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ team_id: userTeamId, amount: amount })
        });
        const res = await response.json();
        if (!res.success) showToast(res.message || "Failed to bid", true);
    } catch(e) { showToast("Error placing bid", true); }
}

// Admin Functions
async function startAuction() {
    if (!currentEventId) return;
    try {
        const response = await fetch(`/api/events/${currentEventId}/auction/start`, {
            method: 'POST',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        const res = await response.json();
        if(!res.success) showToast(res.message, true);
    } catch(e) { showToast("Error", true); }
}

async function pauseAuction() {
    if (!currentEventId) return;
    try {
        const response = await fetch(`/api/events/${currentEventId}/auction/pause`, {
            method: 'POST',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        const res = await response.json();
        if(!res.success) showToast(res.message, true);
    } catch(e) { showToast("Error", true); }
}

async function resumeAuction() {
    if (!currentEventId) return;
    try {
        const response = await fetch(`/api/events/${currentEventId}/auction/resume`, {
            method: 'POST',
            headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
        });
        const res = await response.json();
        if(!res.success) showToast(res.message, true);
    } catch(e) { showToast("Error", true); }
}

async function stopAuction() {
    if (!currentEventId) return;
    if (confirm("Are you sure you want to STOP the auction?")) {
        try {
            const response = await fetch(`/api/events/${currentEventId}/auction/stop`, {
                method: 'POST',
                headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
            });
            const res = await response.json();
            if(!res.success) showToast(res.message, true);
        } catch(e) { showToast("Error", true); }
    }
}

async function nextPlayer() {
    if (!currentEventId) return;
    // Find the next upcoming player from DOM
    let nextPlayerId = null;
    document.querySelectorAll('.queue-item').forEach(el => {
        if (el.querySelector('.status-upcoming') && !nextPlayerId) {
            nextPlayerId = el.id.replace('queue-player-', '');
        }
    });
    
    if (!nextPlayerId) {
        showToast("No more players in queue", true);
        return;
    }
    
    try {
        const response = await fetch(`/api/events/${currentEventId}/auction/player/start`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('token')}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ player_id: nextPlayerId })
        });
        const res = await response.json();
        if(!res.success) showToast(res.message, true);
    } catch(e) { showToast("Error", true); }
}

async function markSold() {
    if (!currentEventId) return;
    if (confirm("Mark current player as SOLD to highest bidder?")) {
        try {
            const response = await fetch(`/api/events/${currentEventId}/auction/player/sell`, {
                method: 'POST',
                headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
            });
            const res = await response.json();
            if(!res.success) showToast(res.message, true);
        } catch(e) { showToast("Error", true); }
    }
}

async function markUnsold() {
    if (!currentEventId) return;
    if (confirm("Mark current player as UNSOLD?")) {
        try {
            const response = await fetch(`/api/events/${currentEventId}/auction/player/unsold`, {
                method: 'POST',
                headers: {'Authorization': `Bearer ${localStorage.getItem('token')}`}
            });
            const res = await response.json();
            if(!res.success) showToast(res.message, true);
        } catch(e) { showToast("Error", true); }
    }
}

function goBack() {
    window.location.href = '/index.html';
}

function showToast(message, isError = false) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.style.background = isError ? 'var(--danger-color)' : 'rgba(15, 23, 42, 0.9)';
    toast.style.color = '#fff';
    toast.style.padding = '12px 24px';
    toast.style.borderRadius = '8px';
    toast.style.boxShadow = '0 10px 15px -3px rgba(0, 0, 0, 0.5)';
    toast.style.border = isError ? 'none' : '1px solid var(--accent-cyan)';
    toast.style.fontWeight = '600';
    toast.style.animation = 'slideIn 0.3s ease-out';
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = 'all 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
