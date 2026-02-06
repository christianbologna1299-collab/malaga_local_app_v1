/**
 * Banker Analytics - Shared Utilities
 * Minimal JS for form handling and UI interactions
 */

// Utility: Validate form inputs
function validateSimulatorForm(formData) {
    const rateShock = parseInt(formData.get('rate_shock'), 10);
    const balanceShock = parseFloat(formData.get('balance_shock'));

    if (isNaN(rateShock) || isNaN(balanceShock)) {
        alert('Invalid form values. Please check your inputs.');
        return false;
    }

    return true;
}

// Utility: Format currency
function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
    }).format(value);
}

// Utility: Format percentage
function formatPercentage(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'percent',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(value);
}

// Utility: Format basis points
function formatBasisPoints(bps) {
    return `${bps > 0 ? '+' : ''}${bps} bps`;
}

// Responsive chart handling
function makeChartsResponsive() {
    // Plotly charts are auto-responsive with config: { responsive: true }
    // This function is a placeholder for future enhancements
    console.debug('Charts configured for responsive rendering');
}

// Phase 2: PDF Export Handler
function exportPDFHandler(sessionId, reportType, resultsData = null) {
    console.log(`Exporting ${reportType} PDF for session ${sessionId}`);

    // Show loading indicator
    showToast(`Generating ${reportType} PDF...`, 'loading');

    // Build request URL and body
    let url = `/${reportType}/${sessionId}/export-pdf`;
    let options = {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
    };

    // Add simulator parameters if applicable
    if (reportType === 'simulator' && resultsData) {
        const body = {
            rate_shock: getSimulatorParam('rate_shock'),
            balance_shock: getSimulatorParam('balance_shock'),
        };
        options.body = JSON.stringify(body);
    }

    // Fetch PDF export
    fetch(url, options)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Export failed: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showToast(`PDF generated successfully (${data.size_mb}MB)`, 'success');
                // Trigger download
                setTimeout(() => {
                    window.location.href = data.download_url;
                }, 500);
            } else {
                showToast(`Error: ${data.error}`, 'error');
            }
        })
        .catch(error => {
            console.error('PDF export error:', error);
            showToast(`Export failed: ${error.message}`, 'error');
        });
}

// Helper: Get simulator form parameter
function getSimulatorParam(paramName) {
    const selector = `input[name="${paramName}"]:checked`;
    const element = document.querySelector(selector);
    return element ? parseFloat(element.value) : 0;
}

// Toast notification (temporary message)
function showToast(message, type = 'info') {
    // Check if toast already exists
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 16px 24px;
            border-radius: 8px;
            color: white;
            font-size: 14px;
            z-index: 10000;
            max-width: 400px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            animation: slideIn 0.3s ease-out;
        `;
        document.body.appendChild(toast);

        // Add animation styles
        if (!document.getElementById('toastStyles')) {
            const style = document.createElement('style');
            style.id = 'toastStyles';
            style.textContent = `
                @keyframes slideIn {
                    from {
                        transform: translateX(100%);
                        opacity: 0;
                    }
                    to {
                        transform: translateX(0);
                        opacity: 1;
                    }
                }
                @keyframes slideOut {
                    from {
                        transform: translateX(0);
                        opacity: 1;
                    }
                    to {
                        transform: translateX(100%);
                        opacity: 0;
                    }
                }
            `;
            document.head.appendChild(style);
        }
    }

    // Set message and type
    toast.textContent = message;

    // Set background color based on type
    switch (type) {
        case 'success':
            toast.style.backgroundColor = '#00FF7F';
            toast.style.color = '#0f0f1e';
            break;
        case 'error':
            toast.style.backgroundColor = '#FF6464';
            toast.style.color = '#ffffff';
            break;
        case 'loading':
            toast.style.backgroundColor = '#00D9FF';
            toast.style.color = '#0f0f1e';
            break;
        default:
            toast.style.backgroundColor = '#666666';
            toast.style.color = '#ffffff';
    }

    // Show toast
    toast.style.display = 'block';
    toast.style.animation = 'slideIn 0.3s ease-out';

    // Auto-hide after 4 seconds (except for loading)
    if (type !== 'loading') {
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => {
                toast.style.display = 'none';
            }, 300);
        }, 4000);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    makeChartsResponsive();
    console.log('Banker Analytics initialized');
});

