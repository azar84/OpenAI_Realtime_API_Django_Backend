// Template Loader for Agent Configuration Admin
document.addEventListener('DOMContentLoaded', function() {
    initializeTemplateLoader();
});

function initializeTemplateLoader() {
    const templateSelect = document.querySelector('#id_instruction_template');
    const instructionsTextarea = document.querySelector('#id_instructions');
    const nameField = document.querySelector('#id_name');
    
    if (!templateSelect || !instructionsTextarea) {
        console.log('Template loader: Required fields not found');
        return;
    }
    
    // Add event listener for template selection
    templateSelect.addEventListener('change', function() {
        const templateId = this.value;
        
        if (!templateId) {
            console.log('No template selected');
            return;
        }
        
        // Get agent name for personalization
        const agentName = nameField ? nameField.value || 'Agent' : 'Agent';
        
        // Show loading state
        const originalInstructions = instructionsTextarea.value;
        instructionsTextarea.value = 'Loading template...';
        instructionsTextarea.disabled = true;
        
        // Fetch template instructions
        fetch(`/api/template-instructions/?template_id=${templateId}&agent_name=${encodeURIComponent(agentName)}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                
                // Ask user for confirmation before replacing instructions
                const hasExistingInstructions = originalInstructions.trim().length > 0;
                let shouldReplace = true;
                
                if (hasExistingInstructions) {
                    shouldReplace = confirm(
                        `This will replace your current instructions with the "${data.template_name}" template.\n\n` +
                        `Template: ${data.template_description}\n\n` +
                        'Do you want to continue?'
                    );
                }
                
                if (shouldReplace) {
                    instructionsTextarea.value = data.instructions;
                    
                    // Show success message
                    showTemplateMessage(
                        `✅ Loaded "${data.template_name}" template. You can now customize these instructions as needed.`,
                        'success'
                    );
                } else {
                    // User cancelled, restore original instructions
                    instructionsTextarea.value = originalInstructions;
                    templateSelect.value = ''; // Clear template selection
                }
            })
            .catch(error => {
                console.error('Error loading template:', error);
                instructionsTextarea.value = originalInstructions;
                
                showTemplateMessage(
                    `❌ Error loading template: ${error.message}`,
                    'error'
                );
            })
            .finally(() => {
                instructionsTextarea.disabled = false;
            });
    });
    
    // Add helpful text near the template field
    addTemplateHelperText(templateSelect);
}

function showTemplateMessage(message, type) {
    // Remove any existing messages
    const existingMessages = document.querySelectorAll('.template-message');
    existingMessages.forEach(msg => msg.remove());
    
    // Create message element
    const messageDiv = document.createElement('div');
    messageDiv.className = `template-message template-message-${type}`;
    messageDiv.style.cssText = `
        margin: 10px 0;
        padding: 10px;
        border-radius: 4px;
        font-size: 12px;
        ${type === 'success' ? 
            'background: #d4edda; color: #155724; border: 1px solid #c3e6cb;' : 
            'background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;'
        }
    `;
    messageDiv.textContent = message;
    
    // Insert message after the template field
    const templateField = document.querySelector('.field-instruction_template');
    if (templateField) {
        templateField.appendChild(messageDiv);
        
        // Auto-remove success messages after 5 seconds
        if (type === 'success') {
            setTimeout(() => {
                if (messageDiv.parentNode) {
                    messageDiv.remove();
                }
            }, 5000);
        }
    }
}

function addTemplateHelperText(templateSelect) {
    const helpText = document.createElement('div');
    helpText.style.cssText = `
        font-size: 11px;
        color: #666;
        margin-top: 5px;
        font-style: italic;
    `;
    helpText.innerHTML = `
        💡 <strong>How it works:</strong> Select a template to populate the instructions field below. 
        You can then customize the instructions as needed. The template is just a starting point.
    `;
    
    const templateField = document.querySelector('.field-instruction_template');
    if (templateField) {
        templateField.appendChild(helpText);
    }
}

// Update instructions when agent name changes (for live preview)
function updateAgentNameInInstructions() {
    const nameField = document.querySelector('#id_name');
    const instructionsTextarea = document.querySelector('#id_instructions');
    
    if (!nameField || !instructionsTextarea) return;
    
    nameField.addEventListener('input', function() {
        const currentInstructions = instructionsTextarea.value;
        const newName = this.value || 'Agent';
        
        // Simple name replacement in instructions (if they contain {name} patterns)
        if (currentInstructions.includes('{name}')) {
            // Don't auto-replace, just show a hint
            showTemplateMessage(
                `💡 Tip: Your instructions contain {name} placeholders. These will be automatically replaced with "${newName}" when the agent runs.`,
                'info'
            );
        }
    });
}

// Initialize name field updates
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(updateAgentNameInInstructions, 100);
});
