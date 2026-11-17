/**
 * Dynamic Sport Ratings & Normalization Thresholds for Player Registration
 * 
 * Fetches the authoritative sport configuration and Normalization Thresholds
 * for the event and renders the required criteria inputs at the end of the
 * registration form with their configured maximum expected values (100/100 score target).
 */

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

async function loadSportRatingsForEvent(eventId) {
    const container = document.getElementById('sportRatingsContainer');
    const inputsContainer = document.getElementById('sportRatingsInputs');

    if (!container || !inputsContainer) {
        console.error('Sport ratings containers not found');
        return;
    }

    // Reset container and show loading state
    inputsContainer.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 1.5rem; color: #94a3b8;">
            <i class="fas fa-spinner fa-spin fa-2x"></i>
            <p style="margin-top: 0.5rem; font-size: 0.9rem;">Loading sport requirements and normalization thresholds...</p>
        </div>
    `;
    container.style.display = 'block';

    try {
        console.log(`Fetching registration configuration for event ${eventId}`);
        const response = await fetch(`/api/events/${eventId}/registration-config`);

        if (response.ok) {
            const data = await response.json();
            console.log('Registration config fetched:', data);

            if (data && Array.isArray(data.fields) && data.fields.length > 0) {
                renderDynamicSportInputs(data, inputsContainer);
                return;
            }
        }

        // Fallback: If registration-config returns no fields or is unavailable, check /api/events/${eventId}/sports
        console.warn(`Falling back to legacy sports check for event ${eventId}`);
        const fallbackRes = await fetch(`/api/events/${eventId}/sports`);
        if (fallbackRes.ok) {
            const sports = await fallbackRes.json();
            if (Array.isArray(sports) && sports.length > 0) {
                renderLegacyFallbackInputs(sports, inputsContainer);
                return;
            }
        }

        // If no sport information at all
        container.style.display = 'none';
        inputsContainer.innerHTML = '';
    } catch (error) {
        console.error('Error loading sport ratings and normalization thresholds:', error);
        container.style.display = 'none';
        inputsContainer.innerHTML = '';
    }
}

function renderDynamicSportInputs(data, inputsContainer) {
    inputsContainer.innerHTML = '';

    const sportName = data.sport_name || 'Sport';
    const cleanSport = sportName.toLowerCase();

    // 1. Sport Header with Normalization Notice
    const headerDiv = document.createElement('div');
    headerDiv.className = 'sport-config-header';
    headerDiv.style.gridColumn = '1 / -1';
    headerDiv.style.marginBottom = '1rem';
    headerDiv.style.paddingBottom = '0.75rem';
    headerDiv.style.borderBottom = '1px solid #334155';

    headerDiv.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;">
            <h5 style="color: #38bdf8; margin: 0; font-size: 1.1rem; display: flex; align-items: center; gap: 0.5rem;">
                <i class="fas fa-trophy"></i>
                <span>${escapeHtml(sportName)} Information</span>
            </h5>
            <span style="font-size: 0.75rem; background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 0.25rem 0.65rem; border-radius: 9999px; font-weight: 500;">
                <i class="fas fa-bullseye"></i> Normalization Thresholds
            </span>
        </div>
        <p style="color: #94a3b8; font-size: 0.825rem; margin: 0.4rem 0 0 0;">
            Please enter your player statistics and profile details for <strong>${escapeHtml(sportName)}</strong>. Scoring is calculated against the sport's normalization thresholds (maximum expected values for 100/100 score).
        </p>
    `;
    inputsContainer.appendChild(headerDiv);

    // 2. Hidden sport rating input for backward compatibility
    if (data.sport_id) {
        const hiddenRating = document.createElement('input');
        hiddenRating.type = 'hidden';
        hiddenRating.className = 'sport-rating-input';
        hiddenRating.dataset.sportId = String(data.sport_id);
        hiddenRating.dataset.sportName = sportName;
        hiddenRating.value = '5';
        inputsContainer.appendChild(hiddenRating);
    }

    // 3. Render Fields (Normalization Thresholds, Roles, Attributes)
    data.fields.forEach(field => {
        const fieldDiv = document.createElement('div');
        fieldDiv.className = 'form-group';
        fieldDiv.style.marginBottom = '1rem';

        const type = String(field.type || 'integer').toLowerCase();
        const hasThreshold = field.maximum !== null && field.maximum !== undefined;
        const unitSuffix = field.unit ? ` (${escapeHtml(field.unit)})` : '';
        const requiredMark = field.required ? ' <span style="color: #ef4444;">*</span>' : '';

        if (type === 'select') {
            // Dropdown for Roles, Attributes, or Categorical Competition Levels
            const options = Array.isArray(field.options) ? field.options : [];
            let optionsHtml = `<option value="">Select ${escapeHtml(field.label)}</option>`;
            options.forEach(opt => {
                const optVal = typeof opt === 'object' && opt !== null ? (opt.value ?? opt.label) : opt;
                const optLabel = typeof opt === 'object' && opt !== null ? (opt.label ?? opt.value) : opt;
                optionsHtml += `<option value="${escapeHtml(String(optVal))}">${escapeHtml(String(optLabel))}</option>`;
            });

            fieldDiv.innerHTML = `
                <label for="profile_${cleanSport}_${escapeHtml(field.key)}" style="color: #e2e8f0; margin-bottom: 0.45rem; display: block; font-weight: 500; font-size: 0.9rem;">
                    ${escapeHtml(field.label)}${requiredMark}
                </label>
                <select id="profile_${cleanSport}_${escapeHtml(field.key)}" 
                        name="profile_${cleanSport}_${escapeHtml(field.key)}" 
                        data-sport="${cleanSport}" 
                        data-attr="${escapeHtml(field.key)}" 
                        data-type="select" 
                        class="form-input sport-profile-input" 
                        ${field.required ? 'required' : ''} 
                        style="width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 0.375rem; background-color: #1e293b; color: #e2e8f0; font-size: 0.95rem;">
                    ${optionsHtml}
                </select>
            `;
        } else if (type === 'text') {
            // Text Field
            fieldDiv.innerHTML = `
                <label for="profile_${cleanSport}_${escapeHtml(field.key)}" style="color: #e2e8f0; margin-bottom: 0.45rem; display: block; font-weight: 500; font-size: 0.9rem;">
                    ${escapeHtml(field.label)}${requiredMark}
                </label>
                <input type="text" 
                       id="profile_${cleanSport}_${escapeHtml(field.key)}" 
                       name="profile_${cleanSport}_${escapeHtml(field.key)}" 
                       data-sport="${cleanSport}" 
                       data-attr="${escapeHtml(field.key)}" 
                       data-type="text" 
                       class="form-input sport-profile-input" 
                       ${field.required ? 'required' : ''} 
                       placeholder="Enter ${escapeHtml(field.label.toLowerCase())}" 
                       style="width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 0.375rem; background-color: #1e293b; color: #e2e8f0; font-size: 0.95rem;">
                ${hasThreshold ? `
                    <small style="color: #94a3b8; font-size: 0.8rem; display: flex; align-items: center; gap: 0.35rem; margin-top: 0.35rem;">
                        <i class="fas fa-bullseye" style="color: #38bdf8;"></i>
                        <span>Normalization threshold: <strong style="color: #38bdf8;">${escapeHtml(String(field.maximum))}</strong></span>
                    </small>
                ` : ''}
            `;
        } else {
            // Numeric Input (Integer or Decimal)
            const isDecimal = type === 'decimal';
            const stepVal = isDecimal ? 'any' : '1';
            const minVal = field.minimum !== null && field.minimum !== undefined ? field.minimum : 0;
            const placeholderText = hasThreshold
                ? `Enter ${field.label.toLowerCase()} (Target for 100/100: ${field.maximum}${field.unit ? ' ' + field.unit : ''})`
                : `Enter ${field.label.toLowerCase()}`;

            fieldDiv.innerHTML = `
                <label for="profile_${cleanSport}_${escapeHtml(field.key)}" style="color: #e2e8f0; margin-bottom: 0.45rem; display: block; font-weight: 500; font-size: 0.9rem;">
                    ${escapeHtml(field.label)}${unitSuffix}${requiredMark}
                </label>
                <input type="number" 
                       id="profile_${cleanSport}_${escapeHtml(field.key)}" 
                       name="profile_${cleanSport}_${escapeHtml(field.key)}" 
                       data-sport="${cleanSport}" 
                       data-attr="${escapeHtml(field.key)}" 
                       data-type="${isDecimal ? 'decimal' : 'integer'}" 
                       class="form-input sport-profile-input" 
                       min="${minVal}" 
                       step="${stepVal}" 
                       ${field.required ? 'required' : ''} 
                       placeholder="${escapeHtml(placeholderText)}" 
                       style="width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 0.375rem; background-color: #1e293b; color: #e2e8f0; font-size: 0.95rem;">
                ${hasThreshold ? `
                    <small style="color: #94a3b8; font-size: 0.8rem; display: flex; align-items: center; gap: 0.35rem; margin-top: 0.35rem;">
                        <i class="fas fa-bullseye" style="color: #38bdf8;"></i>
                        <span>Normalization threshold: <strong style="color: #38bdf8;">${escapeHtml(String(field.maximum))}${field.unit ? ' ' + escapeHtml(field.unit) : ''}</strong> (Max expected value for 100/100 score)</span>
                    </small>
                ` : ''}
            `;
        }

        inputsContainer.appendChild(fieldDiv);
    });
}

function renderLegacyFallbackInputs(sports, inputsContainer) {
    inputsContainer.innerHTML = '';
    sports.forEach(sport => {
        const ratingDiv = document.createElement('div');
        ratingDiv.className = 'form-group';
        ratingDiv.style.marginBottom = '1rem';
        ratingDiv.innerHTML = `
            <label for="sport_${sport.sport_id}" style="color: #e2e8f0; margin-bottom: 0.5rem; display: block;">
                ${escapeHtml(sport.name)} Rating (0-10) *
            </label>
            <input 
                type="number" 
                id="sport_${sport.sport_id}" 
                name="sport_${sport.sport_id}"
                data-sport-id="${sport.sport_id}"
                data-sport-name="${escapeHtml(sport.name)}"
                class="form-input sport-rating-input" 
                min="0" 
                max="10" 
                step="1"
                required
                placeholder="Rate 0-10"
                style="width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 0.375rem; background-color: #1e293b; color: #e2e8f0;"
            />
            <small style="color: #94a3b8; font-size: 0.85rem;">0 = No experience, 10 = Expert</small>
        `;
        inputsContainer.appendChild(ratingDiv);
    });
}

window.loadSportRatingsForEvent = loadSportRatingsForEvent;
