/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const STATUS_CONFIG = {
    all_paid: { label: "All Bills Paid", classes: "badge text-bg-success" },
    partial:  { label: "Partially Paid", classes: "badge text-bg-warning" },
    not_paid: { label: "Bills Unpaid",   classes: "badge text-bg-danger" },
    no_bills: { label: "No Bills",       classes: "badge text-bg-secondary" },
};

export class BillSummaryWidget extends Component {
    static template = "advance_landed_cost.BillSummaryWidget";
    static props = { ...standardFieldProps };

    get statusConfig() {
        return STATUS_CONFIG[this.props.value] || STATUS_CONFIG.no_bills;
    }
}

registry.category("fields").add("bill_summary", {
    component: BillSummaryWidget,
    supportedTypes: ["selection"],
});
