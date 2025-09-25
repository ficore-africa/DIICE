/**
 * Enhanced Real-time Tax Calculator
 * Provides immediate feedback and calculations as users enter data
 */

class TaxCalculatorRealtime {
    constructor() {
        this.form = document.getElementById('taxCalculatorForm');
        this.summaryDiv = document.getElementById('taxSummary');
        this.currentCalculation = null;
        this.calculateTimeout = null;
        this.isCalculating = false;
        
        this.init();
    }
    
    init() {
        if (!this.form || !this.summaryDiv) {
            console.error('Tax calculator elements not found');
            return;
        }
        
        this.bindEvents();
        this.updateCategoryTotals();
        this.showInitialSummary();
    }
    
    bindEvents() {
        // Real-time input updates
        const inputs = this.form.querySelectorAll('input[type="number"]');
        inputs.forEach(input => {
            input.addEventListener('input', (e) => this.handleInputChange(e));
            input.addEventListener('blur', (e) => this.handleInputBlur(e));
        });
        
        // Form submission
        this.form.addEventListener('submit', (e) => this.handleFormSubmit(e));
        
        // Clear form
        const clearButton = document.getElementById('clearForm');
        if (clearButton) {
            clearButton.addEventListener('click', () => this.clearForm());
        }
    }
    
    handleInputChange(event) {
        const input = event.target;
        
        // Update category totals immediately
        this.updateCategoryTotals();
        
        // Debounced calculation
        clearTimeout(this.calculateTimeout);
        this.calculateTimeout = setTimeout(() => {
            this.performRealtimeCalculation();
        }, 800);
        
        // Visual feedback
        this.addInputFeedback(input);
    }
    
    handleInputBlur(event) {
        const input = event.target;
        this.validateInput(input);
    }
    
    addInputFeedback(input) {
        // Add subtle animation to show input is being processed
        input.classList.add('updating');
        setTimeout(() => {
            input.classList.remove('updating');
        }, 300);
    }
    
    validateInput(input) {
        const value = parseFloat(input.value) || 0;
        
        // Remove existing validation classes
        input.classList.remove('is-valid', 'is-invalid');
        
        if (input.value && value < 0) {
            input.classList.add('is-invalid');
            this.showInputError(input, 'Amount cannot be negative');
        } else if (input.value && value > 0) {
            input.classList.add('is-valid');
            this.clearInputError(input);
        }
    }
    
    showInputError(input, message) {
        let errorDiv = input.parentNode.querySelector('.invalid-feedback');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'invalid-feedback';
            input.parentNode.appendChild(errorDiv);
        }
        errorDiv.textContent = message;
    }
    
    clearInputError(input) {
        const errorDiv = input.parentNode.querySelector('.invalid-feedback');
        if (errorDiv) {
            errorDiv.remove();
        }
    }
    
    updateCategoryTotals() {
        let deductibleTotal = 0;
        let statutoryTotal = 0;
        let personalTotal = 0;
        
        const expenseInputs = this.form.querySelectorAll('.expense-input');
        expenseInputs.forEach(input => {
            const amount = parseFloat(input.value) || 0;
            const categoryType = input.getAttribute('data-category-type');
            
            switch(categoryType) {
                case 'deductible':
                    deductibleTotal += amount;
                    break;
                case 'statutory':
                    statutoryTotal += amount;
                    break;
                case 'personal':
                    personalTotal += amount;
                    break;
            }
        });
        
        // Update display with animation
        this.animateValueUpdate('deductibleTotal', deductibleTotal);
        this.animateValueUpdate('statutoryTotal', statutoryTotal);
        this.animateValueUpdate('personalTotal', personalTotal);
    }
    
    animateValueUpdate(elementId, newValue) {
        const element = document.getElementById(elementId);
        if (!element) return;
        
        const formattedValue = this.formatCurrency(newValue);
        
        // Add updating class for animation
        element.classList.add('updating');
        
        setTimeout(() => {
            element.textContent = formattedValue;
            element.classList.remove('updating');
        }, 150);
    }
    
    performRealtimeCalculation() {
        if (this.isCalculating) return;
        
        const totalIncome = parseFloat(document.getElementById('total_income').value) || 0;
        
        // Only calculate if there's income
        if (totalIncome <= 0) {
            this.showInitialSummary();
            return;
        }
        
        this.isCalculating = true;
        this.showCalculatingState();
        
        // Collect form data
        const data = this.collectFormData();
        
        // Send real-time calculation request
        fetch('/tax/calculate-realtime', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(result => {
            this.isCalculating = false;
            
            if (result.success) {
                this.currentCalculation = result.breakdown;
                this.updateRealtimeSummary(result.breakdown);
            } else {
                this.showCalculationError(result.message || 'Calculation error');
            }
        })
        .catch(error => {
            this.isCalculating = false;
            console.error('Real-time calculation error:', error);
            this.showCalculationError('Network error during calculation');
        });
    }
    
    collectFormData() {
        const formData = new FormData(this.form);
        
        // Collect categorized expenses
        const expenses = {};
        const expenseInputs = this.form.querySelectorAll('.expense-input');
        expenseInputs.forEach(input => {
            const categoryKey = input.name;
            const amount = parseFloat(input.value) || 0;
            expenses[categoryKey] = amount;
        });
        
        return {
            total_income: parseFloat(formData.get('total_income')) || 0,
            annual_rent: parseFloat(formData.get('annual_rent')) || 0,
            expenses: expenses,
            realtime: true
        };
    }
    
    showCalculatingState() {
        this.summaryDiv.innerHTML = `
            <div class="text-center py-4">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Calculating...</span>
                </div>
                <p class="text-muted">Calculating your tax...</p>
            </div>
        `;
    }
    
    updateRealtimeSummary(breakdown) {
        if (!breakdown) return;
        
        let summaryHtml = '';
        
        if (breakdown.calculation_type === 'CIT') {
            summaryHtml = this.generateCITSummary(breakdown);
        } else {
            summaryHtml = this.generatePITSummary(breakdown);
        }
        
        this.summaryDiv.innerHTML = summaryHtml;
    }
    
    generatePITSummary(breakdown) {
        const summary = breakdown.summary || {};
        const effectiveRate = summary.effective_tax_rate || 0;
        
        return `
            <div class="tax-summary-content">
                <div class="summary-header mb-3">
                    <h5 class="text-primary mb-1">
                        <i class="fas fa-calculator"></i> Tax Calculation Summary
                    </h5>
                    <small class="text-muted">Personal Income Tax (PIT)</small>
                </div>
                
                <div class="summary-metrics">
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label">Total Income:</span>
                            <span class="metric-value text-success fw-bold">${this.formatCurrency(summary.total_income || 0)}</span>
                        </div>
                    </div>
                    
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label">Deductible Expenses:</span>
                            <span class="metric-value text-info">${this.formatCurrency(summary.total_deductible_expenses || 0)}</span>
                        </div>
                    </div>
                    
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label">Statutory Expenses:</span>
                            <span class="metric-value text-info">${this.formatCurrency(summary.statutory_expenses || 0)}</span>
                        </div>
                    </div>
                    
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label">Rent Relief:</span>
                            <span class="metric-value text-warning">${this.formatCurrency(summary.rent_relief || 0)}</span>
                        </div>
                    </div>
                    
                    <hr>
                    
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label fw-bold">Taxable Income:</span>
                            <span class="metric-value text-primary fw-bold">${this.formatCurrency(summary.final_taxable_income || 0)}</span>
                        </div>
                    </div>
                    
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label fw-bold text-danger">Tax Liability:</span>
                            <span class="metric-value text-danger fw-bold fs-5">${this.formatCurrency(summary.tax_liability || 0)}</span>
                        </div>
                    </div>
                    
                    <div class="metric-item">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label">Effective Tax Rate:</span>
                            <span class="metric-value text-secondary">${effectiveRate.toFixed(2)}%</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-actions mt-4">
                    <button type="button" class="btn btn-primary btn-sm w-100" onclick="taxCalculator.showDetailedBreakdown()">
                        <i class="fas fa-chart-line"></i> View Detailed Breakdown
                    </button>
                </div>
            </div>
        `;
    }
    
    generateCITSummary(breakdown) {
        const effectiveRate = breakdown.effective_tax_rate || 0;
        const isExempt = breakdown.exemption_applied || false;
        
        return `
            <div class="tax-summary-content">
                <div class="summary-header mb-3">
                    <h5 class="text-primary mb-1">
                        <i class="fas fa-building"></i> Tax Calculation Summary
                    </h5>
                    <small class="text-muted">Companies Income Tax (CIT)</small>
                </div>
                
                <div class="summary-metrics">
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label">Total Revenue:</span>
                            <span class="metric-value text-success fw-bold">${this.formatCurrency(breakdown.total_revenue || 0)}</span>
                        </div>
                    </div>
                    
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label">Total Expenses:</span>
                            <span class="metric-value text-info">${this.formatCurrency(breakdown.total_expenses || 0)}</span>
                        </div>
                    </div>
                    
                    <hr>
                    
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label fw-bold">Taxable Income:</span>
                            <span class="metric-value text-primary fw-bold">${this.formatCurrency(breakdown.taxable_income || 0)}</span>
                        </div>
                    </div>
                    
                    ${isExempt ? `
                        <div class="alert alert-success py-2 mb-3">
                            <small><i class="fas fa-check-circle"></i> Small Company Exemption Applied</small>
                        </div>
                    ` : ''}
                    
                    <div class="metric-item mb-3">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label fw-bold text-danger">Tax Liability:</span>
                            <span class="metric-value text-danger fw-bold fs-5">${this.formatCurrency(breakdown.tax_liability || 0)}</span>
                        </div>
                    </div>
                    
                    <div class="metric-item">
                        <div class="d-flex justify-content-between align-items-center">
                            <span class="metric-label">Effective Tax Rate:</span>
                            <span class="metric-value text-secondary">${effectiveRate.toFixed(2)}%</span>
                        </div>
                    </div>
                </div>
                
                <div class="summary-actions mt-4">
                    <button type="button" class="btn btn-primary btn-sm w-100" onclick="taxCalculator.showDetailedBreakdown()">
                        <i class="fas fa-chart-line"></i> View Detailed Breakdown
                    </button>
                </div>
            </div>
        `;
    }
    
    showInitialSummary() {
        this.summaryDiv.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="fas fa-calculator fa-3x mb-3"></i>
                <p>Enter your income and expenses to see your tax calculation</p>
                <small class="text-muted">Real-time calculations will appear as you type</small>
            </div>
        `;
    }
    
    showCalculationError(message) {
        this.summaryDiv.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-exclamation-triangle text-warning fa-2x mb-3"></i>
                <p class="text-muted">${message}</p>
                <small class="text-muted">Please check your inputs and try again</small>
            </div>
        `;
    }
    
    handleFormSubmit(event) {
        event.preventDefault();
        
        // If we have a current calculation, show detailed modal
        if (this.currentCalculation) {
            this.showDetailedBreakdown();
        } else {
            // Perform full calculation
            this.performFullCalculation();
        }
    }
    
    performFullCalculation() {
        const data = this.collectFormData();
        data.realtime = false; // Full calculation
        
        // Show loading modal if available
        const loadingModal = document.getElementById('loadingModal');
        if (loadingModal) {
            new bootstrap.Modal(loadingModal).show();
        }
        
        fetch('/tax/calculate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => response.json())
        .then(result => {
            if (loadingModal) {
                bootstrap.Modal.getInstance(loadingModal).hide();
            }
            
            if (result.success) {
                this.currentCalculation = result.breakdown;
                this.updateRealtimeSummary(result.breakdown);
                this.showDetailedBreakdown();
            } else {
                this.showAlert('danger', 'Error calculating tax: ' + (result.message || result.error));
            }
        })
        .catch(error => {
            if (loadingModal) {
                bootstrap.Modal.getInstance(loadingModal).hide();
            }
            console.error('Error:', error);
            this.showAlert('danger', 'An error occurred while calculating tax. Please try again.');
        });
    }
    
    showDetailedBreakdown() {
        if (!this.currentCalculation) {
            this.performFullCalculation();
            return;
        }
        
        // Show detailed modal if available
        const modal = document.getElementById('taxSummaryModal');
        if (modal) {
            // Update modal content with current calculation
            this.updateModalContent(this.currentCalculation);
            new bootstrap.Modal(modal).show();
        }
    }
    
    updateModalContent(breakdown) {
        const modalBody = document.getElementById('taxSummaryModalBody');
        if (!modalBody) return;
        
        // Generate detailed modal content based on calculation type
        if (breakdown.calculation_type === 'CIT') {
            modalBody.innerHTML = this.generateDetailedCITModal(breakdown);
        } else {
            modalBody.innerHTML = this.generateDetailedPITModal(breakdown);
        }
    }
    
    generateDetailedPITModal(breakdown) {
        const fourStep = breakdown.four_step_breakdown || {};
        
        return `
            <div class="detailed-breakdown">
                <h5 class="mb-4">Four-Step PIT Calculation Breakdown</h5>
                
                ${this.generateStepCard(fourStep.step1, 1, 'success')}
                ${this.generateStepCard(fourStep.step2, 2, 'info')}
                ${this.generateStepCard(fourStep.step3, 3, 'warning')}
                ${this.generateStepCard(fourStep.step4, 4, 'primary')}
                
                <div class="final-summary mt-4">
                    <div class="card border-danger">
                        <div class="card-header bg-danger text-white">
                            <h6 class="mb-0">Final Tax Summary</h6>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-6">
                                    <strong>Tax Liability:</strong>
                                </div>
                                <div class="col-6 text-end">
                                    <strong class="text-danger fs-5">${this.formatCurrency(breakdown.summary?.tax_liability || 0)}</strong>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    generateDetailedCITModal(breakdown) {
        const steps = breakdown.calculation_steps || [];
        
        return `
            <div class="detailed-breakdown">
                <h5 class="mb-4">CIT Calculation Breakdown</h5>
                
                ${steps.map(step => `
                    <div class="step-card mb-3">
                        <div class="card">
                            <div class="card-header">
                                <h6 class="mb-0">Step ${step.step}: ${step.description}</h6>
                            </div>
                            <div class="card-body">
                                <p class="mb-2">${step.calculation}</p>
                                <div class="text-end">
                                    <strong>${typeof step.result === 'number' ? this.formatCurrency(step.result) : step.result}</strong>
                                </div>
                            </div>
                        </div>
                    </div>
                `).join('')}
                
                <div class="final-summary mt-4">
                    <div class="card border-danger">
                        <div class="card-header bg-danger text-white">
                            <h6 class="mb-0">Final Tax Summary</h6>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-6">
                                    <strong>Tax Liability:</strong>
                                </div>
                                <div class="col-6 text-end">
                                    <strong class="text-danger fs-5">${this.formatCurrency(breakdown.tax_liability || 0)}</strong>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    generateStepCard(stepData, stepNumber, colorClass) {
        if (!stepData) return '';
        
        return `
            <div class="step-card mb-3">
                <div class="card border-${colorClass}">
                    <div class="card-header bg-${colorClass} text-white">
                        <h6 class="mb-0">Step ${stepNumber}: ${stepData.step_name || 'Calculation Step'}</h6>
                    </div>
                    <div class="card-body">
                        <p class="small text-muted mb-2">${stepData.description || ''}</p>
                        <div class="calculation-formula mb-2">
                            <code class="small">${stepData.formula || ''}</code>
                        </div>
                        ${stepData.calculation_note ? `
                            <small class="text-info d-block">
                                <i class="fas fa-info-circle"></i> ${stepData.calculation_note}
                            </small>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }
    
    clearForm() {
        this.form.reset();
        this.currentCalculation = null;
        this.updateCategoryTotals();
        this.showInitialSummary();
        
        // Clear validation classes
        const inputs = this.form.querySelectorAll('input');
        inputs.forEach(input => {
            input.classList.remove('is-valid', 'is-invalid');
        });
        
        // Clear error messages
        const errorDivs = this.form.querySelectorAll('.invalid-feedback');
        errorDivs.forEach(div => div.remove());
    }
    
    formatCurrency(amount) {
        return new Intl.NumberFormat('en-NG', {
            style: 'currency',
            currency: 'NGN',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(amount || 0);
    }
    
    showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // Insert at top of page
        const container = document.querySelector('.container-fluid');
        if (container) {
            container.insertBefore(alertDiv, container.firstChild);
            
            // Auto-dismiss after 5 seconds
            setTimeout(() => {
                if (alertDiv.parentNode) {
                    alertDiv.remove();
                }
            }, 5000);
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.taxCalculator = new TaxCalculatorRealtime();
});