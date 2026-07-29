
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
        sports.forEach(sport => {
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
        });

        // Show the container
        container.style.display = 'block';
        console.log(`Added ${sports.length} sport rating inputs`);

    } catch (error) {
        console.error('Error loading sport ratings:', error);
        container.style.display = 'none';
    }
}
