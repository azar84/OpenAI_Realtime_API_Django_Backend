// Custom JavaScript for Agent Configuration Admin
document.addEventListener('DOMContentLoaded', function() {
    initializeSliders();
});

function updateSliderValue(slider) {
    // Find or create the value display element
    let valueDisplay = slider.parentNode.querySelector('.slider-value-display');
    
    if (!valueDisplay) {
        valueDisplay = document.createElement('span');
        valueDisplay.className = 'slider-value-display';
        valueDisplay.style.cssText = `
            margin-left: 10px;
            font-weight: bold;
            color: #0073aa;
            background: #f0f0f1;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
        `;
        slider.parentNode.appendChild(valueDisplay);
    }
    
    // Update the display value
    const value = parseFloat(slider.value);
    const suffix = slider.getAttribute('data-suffix') || '';
    
    // Format value based on field type
    let displayValue = value;
    if (slider.classList.contains('temperature-slider')) {
        displayValue = value.toFixed(1);
        if (value <= 0.7) {
            valueDisplay.style.color = '#0073aa'; // Blue for focused
        } else if (value <= 1.0) {
            valueDisplay.style.color = '#00a32a'; // Green for balanced
        } else {
            valueDisplay.style.color = '#d63638'; // Red for creative
        }
    } else if (slider.classList.contains('vad-slider')) {
        displayValue = value.toFixed(1);
        if (value <= 0.3) {
            valueDisplay.style.color = '#d63638'; // Red for very sensitive
        } else if (value <= 0.7) {
            valueDisplay.style.color = '#00a32a'; // Green for good range
        } else {
            valueDisplay.style.color = '#0073aa'; // Blue for less sensitive
        }
    }
    
    valueDisplay.textContent = displayValue + suffix;
}

function initializeSliders() {
    // Initialize all sliders with value displays
    const sliders = document.querySelectorAll('.slider-with-value');
    
    sliders.forEach(function(slider) {
        // Set initial value display
        updateSliderValue(slider);
        
        // Add helpful labels
        if (slider.classList.contains('temperature-slider')) {
            addSliderLabels(slider, '0.6\n(Focused)', '1.2\n(Creative)');
        } else if (slider.classList.contains('vad-slider')) {
            addSliderLabels(slider, '0.0\n(Sensitive)', '1.0\n(Loud Audio)');
        }
    });
}

function addSliderLabels(slider, leftLabel, rightLabel) {
    const container = document.createElement('div');
    container.style.cssText = `
        display: flex;
        justify-content: space-between;
        font-size: 10px;
        color: #666;
        margin-top: 2px;
        white-space: pre-line;
        text-align: center;
    `;
    
    const leftSpan = document.createElement('span');
    leftSpan.textContent = leftLabel;
    
    const rightSpan = document.createElement('span');
    rightSpan.textContent = rightLabel;
    
    container.appendChild(leftSpan);
    container.appendChild(rightSpan);
    
    slider.parentNode.appendChild(container);
}
