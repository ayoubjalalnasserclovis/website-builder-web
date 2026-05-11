document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('generate-form');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnIcon = submitBtn.querySelector('.btn-icon');
    const spinner = submitBtn.querySelector('.spinner');
    
    const resultContainer = document.getElementById('result-container');
    const errorContainer = document.getElementById('error-container');
    const previewLink = document.getElementById('preview-link');
    const costDisplay = document.getElementById('cost-display');
    const errorMessage = document.getElementById('error-message');

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Reset states
        resultContainer.classList.add('hidden');
        errorContainer.classList.add('hidden');
        
        // Set loading state
        submitBtn.disabled = true;
        btnText.textContent = 'Generating (takes ~20-40s)...';
        btnIcon.style.display = 'none';
        spinner.style.display = 'block';
        submitBtn.style.opacity = '0.7';

        const formData = new FormData(form);
        const requestData = {
            input_data: formData.get('input_data'),
            company_name: formData.get('company_name')
        };

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            if (data.success) {
                // Show success
                previewLink.href = data.url;
                costDisplay.textContent = `Cost: $${(data.cost_usd || 0).toFixed(4)}`;
                resultContainer.classList.remove('hidden');
                
                // Optional: add a slight micro-animation
                resultContainer.style.transform = 'scale(0.98)';
                setTimeout(() => resultContainer.style.transform = 'scale(1)', 50);
            } else {
                // Show error
                throw new Error(data.error || 'Failed to generate website');
            }
            
        } catch (error) {
            errorMessage.textContent = error.message || 'An unexpected error occurred. Please try again.';
            errorContainer.classList.remove('hidden');
        } finally {
            // Restore button state
            submitBtn.disabled = false;
            btnText.textContent = 'Generate Improved Site';
            btnIcon.style.display = 'inline-block';
            spinner.style.display = 'none';
            submitBtn.style.opacity = '1';
        }
    });
});
