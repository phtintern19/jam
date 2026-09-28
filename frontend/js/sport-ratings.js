
// Load sports for the selected event and create rating inputs
async function loadSportRatingsForEvent(eventId) {
    const container = document.getElementById('sportRatingsContainer');
    const inputsContainer = document.getElementById('sportRatingsInputs');

    if (!container || !inputsContainer) {
        console.error('Sport ratings containers not found');
        return;
    }

    try {
        console.log(`Fetching sports for event ${eventId}`);

        // Fetch sports for this event
        const response = await fetch(`/api/events/${eventId}/sports`);
        if (!response.ok) {
            console.error('Failed to fetch sports for event');
            container.style.display = 'none';
            return;
        }

        const sports = await response.json();
        console.log('Sports fetched:', sports);

        if (sports.length === 0) {
            console.log('No sports found for this event');
            container.style.display = 'none';
            return;
        }

        // Clear previous inputs
        inputsContainer.innerHTML = '';

        // Create rating input for each sport
        for (const sport of sports) {
            const isCricket = sport.name.toLowerCase() === 'cricket';

            if (!isCricket) {
                const ratingDiv = document.createElement('div');
                ratingDiv.className = 'form-group';
                ratingDiv.style.marginBottom = '1rem';

                ratingDiv.innerHTML = `
                    <label for="sport_${sport.sport_id}" style="color: #e2e8f0; margin-bottom: 0.5rem; display: block;">
                        ${sport.name} *
                    </label>
                    <input 
                        type="number" 
                        id="sport_${sport.sport_id}" 
                        name="sport_${sport.sport_id}"
                        data-sport-id="${sport.sport_id}"
                        data-sport-name="${sport.name}"
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
            }
            
            // --- CRICKET SPORT MASTER INTEGRATION ---
            if (isCricket) {
                // Add a header for Cricket
                const headerDiv = document.createElement('div');
                headerDiv.style.marginTop = '1rem';
                headerDiv.style.marginBottom = '1rem';
                headerDiv.style.borderBottom = '1px solid #334155';
                headerDiv.style.paddingBottom = '0.5rem';
                headerDiv.innerHTML = `<h5 style="color: #38bdf8; margin: 0; font-size: 1.05rem;"><i class="fas fa-cricket-bat-ball"></i> Cricket Information</h5>`;
                inputsContainer.appendChild(headerDiv);

                try {
                    const masterRes = await fetch(`/api/sports/${sport.sport_id}`);
                    if (masterRes.ok) {
                        const masterData = await masterRes.json();
                        if (masterData.success && masterData.sport) {
                            
                            // 1. Render Role Dropdown
                            if (masterData.sport.roles_config && masterData.sport.roles_config.length > 0) {
                                const roleDiv = document.createElement('div');
                                roleDiv.className = 'form-group';
                                roleDiv.style.marginBottom = '1rem';
                                
                                let selectHtml = `<select id="profile_${sport.name}_role" data-sport="${sport.name}" data-attr="role" class="form-input sport-profile-input" required style="width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 0.375rem; background-color: #1e293b; color: #e2e8f0;">`;
                                selectHtml += `<option value="">Select Primary Role</option>`;
                                masterData.sport.roles_config.forEach(role => {
                                    selectHtml += `<option value="${role}">${role}</option>`;
                                });
                                selectHtml += `</select>`;
                                
                                roleDiv.innerHTML = `
                                    <label for="profile_${sport.name}_role" style="color: #e2e8f0; margin-bottom: 0.5rem; display: block;">
                                        Playing Role *
                                    </label>
                                    ${selectHtml}
                                `;
                                inputsContainer.appendChild(roleDiv);
                            }

                            // 2. Render Attributes Schema (Batting Style, Bowling Style)
                            if (masterData.sport.attributes_schema) {
                                const schema = masterData.sport.attributes_schema;
                                for (const [attrName, options] of Object.entries(schema)) {
                                    const attrDiv = document.createElement('div');
                                    attrDiv.className = 'form-group';
                                    attrDiv.style.marginBottom = '1rem';
                                    
                                    const niceName = attrName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                                    
                                    let selectHtml = `<select id="profile_${sport.name}_${attrName}" data-sport="${sport.name}" data-attr="${attrName}" class="form-input sport-profile-input" required style="width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 0.375rem; background-color: #1e293b; color: #e2e8f0;">`;
                                    selectHtml += `<option value="">Select ${niceName}</option>`;
                                    options.forEach(opt => {
                                        selectHtml += `<option value="${opt}">${opt}</option>`;
                                    });
                                    selectHtml += `</select>`;
                                    
                                    attrDiv.innerHTML = `
                                        <label for="profile_${sport.name}_${attrName}" style="color: #e2e8f0; margin-bottom: 0.5rem; display: block;">
                                            ${niceName} *
                                        </label>
                                        ${selectHtml}
                                    `;
                                    inputsContainer.appendChild(attrDiv);
                                }
                            }
                        }
                    }
                } catch(e) {
                    console.error("Failed to load sport master attributes schema", e);
                }

                // 3. Add Factual Information Fields
                const isBadminton = sport.name.toLowerCase() === 'badminton';
                const factualFields = isBadminton 
                    ? [
                        { id: 'matches_played', label: 'Matches Played', type: 'number', min: '0' },
                        { id: 'win_rate', label: 'Win Rate (%)', type: 'number', min: '0' },
                        { id: 'tournaments_won', label: 'Tournaments Won', type: 'number', min: '0' },
                        { id: 'years_experience', label: 'Years of Experience', type: 'number', min: '0' }
                    ]
                    : [
                        { id: 'matches_played', label: 'Matches Played', type: 'number', min: '0' },
                        { id: 'runs', label: 'Runs', type: 'number', min: '0' },
                        { id: 'wickets', label: 'Wickets', type: 'number', min: '0' },
                        { id: 'years_experience', label: 'Years of Experience', type: 'number', min: '0' }
                    ];
                
                factualFields.forEach(field => {
                    const fieldDiv = document.createElement('div');
                    fieldDiv.className = 'form-group';
                    fieldDiv.style.marginBottom = '1rem';
                    fieldDiv.innerHTML = `
                        <label for="profile_${sport.name}_${field.id}" style="color: #e2e8f0; margin-bottom: 0.5rem; display: block;">
                            ${field.label} *
                        </label>
                        <input type="${field.type}" id="profile_${sport.name}_${field.id}" 
                               data-sport="${sport.name}" data-attr="${field.id}" 
                               class="form-input sport-profile-input" min="${field.min}" required 
                               placeholder="Enter ${field.label.toLowerCase()}"
                               style="width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 0.375rem; background-color: #1e293b; color: #e2e8f0;">
                    `;
                    inputsContainer.appendChild(fieldDiv);
                });
                
                // 4. Add Highest Level Played Dropdown
                const levelDiv = document.createElement('div');
                levelDiv.className = 'form-group';
                levelDiv.style.marginBottom = '1rem';
                levelDiv.innerHTML = `
                    <label for="profile_${sport.name}_highest_level" style="color: #e2e8f0; margin-bottom: 0.5rem; display: block;">
                        Highest Level Played *
                    </label>
                    <select id="profile_${sport.name}_highest_level" data-sport="${sport.name}" data-attr="highest_level" class="form-input sport-profile-input" required style="width: 100%; padding: 0.75rem; border: 1px solid #475569; border-radius: 0.375rem; background-color: #1e293b; color: #e2e8f0;">
                        <option value="">Select Level</option>
                        <option value="Local">Local / Club</option>
                        <option value="District">District</option>
                        <option value="State">State</option>
                        <option value="National">National</option>
                        <option value="Professional">Professional</option>
                        <option value="International">International</option>
                    </select>
                `;
                inputsContainer.appendChild(levelDiv);
            }
        }

        // Show the container
        container.style.display = 'block';
        console.log(`Added ${sports.length} sport rating inputs`);

    } catch (error) {
        console.error('Error loading sport ratings:', error);
        container.style.display = 'none';
    }
}
