/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useRef, useState } from "@odoo/owl";

export class SpanShipmentOpeningScreen extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");

        // State for print reports section
        this.state = useState({
            selectedPickingId: false,
            selectedPickingName: "",
            searchQuery: "",
            searchType: "picking", // Add this - default to picking
            selectedBatchId: false, // Add this
            selectedBatchName: "", // Add this
        });

        this.pickingSearchInput = useRef("pickingSearchInput");
    }

    async searchPicking() {
        const searchQuery = this.pickingSearchInput.el?.value?.trim();
        if (!searchQuery) {
            this.resetSelection();
            this.notification.add("Please enter an order number", {
                type: "warning",
                title: "Input Required",
            });
            return;
        }

        try {
            if (this.state.searchType === "picking") {
                // Search for picking
                const pickings = await this.orm.searchRead(
                    "stock.picking",
                    [["name", "ilike", searchQuery]],
                    ["id", "name", "partner_id", "state"],
                    { limit: 1 }
                );

                if (pickings && pickings.length > 0) {
                    this.state.selectedPickingId = pickings[0].id;
                    this.state.selectedPickingName = pickings[0].name;
                    this.state.selectedBatchId = false;
                    this.state.selectedBatchName = "";
                    this.notification.add(`Selected: ${pickings[0].name}`, {
                        type: "success",
                        title: "Order Found",
                    });
                } else {
                    this.notification.add(`No picking order found matching "${searchQuery}"`, {
                        type: "warning",
                        title: "Not Found",
                    });
                    this.resetSelection();
                }
            } else {
                // Search for batch
                const batches = await this.orm.searchRead(
                    "stock.picking.batch",
                    [["name", "ilike", searchQuery]],
                    ["id", "name", "state"],
                    { limit: 1 }
                );

                if (batches && batches.length > 0) {
                    this.state.selectedBatchId = batches[0].id;
                    this.state.selectedBatchName = batches[0].name;
                    this.state.selectedPickingId = false;
                    this.state.selectedPickingName = "";
                    this.notification.add(`Selected: ${batches[0].name}`, {
                        type: "success",
                        title: "Batch Found",
                    });
                } else {
                    this.notification.add(`No batch found matching "${searchQuery}"`, {
                        type: "warning",
                        title: "Not Found",
                    });
                    this.resetSelection();
                }
            }
        } catch (error) {
            console.error("Error searching:", error);
            this.notification.add("Error searching for order", {
                type: "danger",
                title: "Search Error",
            });
        }
    }

    resetSelection() {
        this.state.selectedPickingId = false;
        this.state.selectedPickingName = "";
        this.state.selectedBatchId = false;
        this.state.selectedBatchName = "";
    }

    toggleSearchType(type) {
        this.state.searchType = type;
        this.resetSelection();
        if (this.pickingSearchInput.el) {
            this.pickingSearchInput.el.value = "";
        }
    }

    // Main Operations Section

    async openBarcodeScanning() {
        // Open barcode app main menu
        await this.action.doAction({
            type: "ir.actions.client",
            name: "Barcode",
            tag: "stock_barcode_main_menu",
            params: {},
        });
    }

    async createBatch() {
        // Open list of PICKING orders (not delivery) ready for batch creation
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Create Batch - Select Picking Orders",
            res_model: "stock.picking",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["picking_type_id.code", "=", "internal"],  // Changed to internal for picking orders
                ["state", "in", ["draft", "waiting", "confirmed", "assigned"]],  // Include all relevant states
                ["batch_id", "=", false]
            ],
            context: {
                search_default_ready: 1,
                create_batch_mode: true,
            },
        });
    }

    async packAndGetRates() {
        // This method is no longer used directly
        // The card now has two buttons that call the methods below
    }

    async showPickingOrdersForRates() {
        // Show picking orders for pack and rate
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Select Picking Orders for Pack & Rate",
            res_model: "stock.picking",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["picking_type_id.code", "=", "internal"],
                ["state", "in", ["draft", "waiting", "confirmed", "assigned"]]
            ],
            context: {
                default_picking_type_code: "internal",
                pack_and_rate_mode: true,
            },
        });
    }

    async showBatchPickingsForRates() {
        // Show batch pickings for pack and rate
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Select Batch Pickings for Pack & Rate",
            res_model: "stock.picking.batch",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["state", "in", ["draft", "in_progress"]]
            ],
            context: {
                pack_and_rate_mode: true,
            },
        });
    }

    async viewProducts() {
        // Open products list
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Products",
            res_model: "product.product",
            view_mode: "list,form,kanban",
            views: [[false, "list"], [false, "form"], [false, "kanban"]],
        });
    }

    async printReports() {
        if (!this.state.selectedPickingId && !this.state.selectedBatchId) {
            this.notification.add("Please search and select an order or batch first", {
                type: "warning",
                title: "No Selection",
            });
            return;
        }

        if (this.state.selectedBatchId) {
            // Open batch form for all reports
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Print Shipping Reports - Batch",
                res_model: "stock.picking.batch",
                res_id: this.state.selectedBatchId,
                view_mode: "form",
                views: [[false, "form"]],
                target: "current",
                context: {
                    print_report_mode: true,
                },
            });
        } else {
            // Open picking form for all reports
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Print Shipping Reports",
                res_model: "stock.picking",
                res_id: this.state.selectedPickingId,
                view_mode: "form",
                views: [[false, "form"]],
                target: "current",
                context: {
                    print_report_mode: true,
                },
            });
        }
    }

    async printContainerLabel() {
        if (!this.state.selectedPickingId && !this.state.selectedBatchId) {
            this.notification.add("Please search and select an order or batch first", {
                type: "warning",
                title: "No Selection",
            });
            return;
        }

        const reportName = this.state.selectedBatchId
            ? "span_shipment.report_container_label_batch"
            : "span_shipment.report_container_label_picking";

        const recordId = this.state.selectedBatchId || this.state.selectedPickingId;
        const modelName = this.state.selectedBatchId ? "stock.picking.batch" : "stock.picking";

        await this.action.doAction({
            type: "ir.actions.report",
            report_name: reportName,
            report_type: "qweb-pdf",
            data: null,
            context: {
                active_ids: [recordId],
                active_model: modelName,
            },
        });
    }

    async printBillOfLading() {
        if (!this.state.selectedPickingId && !this.state.selectedBatchId) {
            this.notification.add("Please search and select an order or batch first", {
                type: "warning",
                title: "No Selection",
            });
            return;
        }

        const reportName = this.state.selectedBatchId
            ? "span_shipment.report_bill_of_lading_batch"
            : "span_shipment.report_bill_of_lading_picking";

        const recordId = this.state.selectedBatchId || this.state.selectedPickingId;
        const modelName = this.state.selectedBatchId ? "stock.picking.batch" : "stock.picking";

        await this.action.doAction({
            type: "ir.actions.report",
            report_name: reportName,
            report_type: "qweb-pdf",
            data: null,
            context: {
                active_ids: [recordId],
                active_model: modelName,
            },
        });
    }

    async printPackingList() {
        if (!this.state.selectedPickingId && !this.state.selectedBatchId) {
            this.notification.add("Please search and select an order or batch first", {
                type: "warning",
                title: "No Selection",
            });
            return;
        }

        const reportName = this.state.selectedBatchId
            ? "span_shipment.report_packing_list_batch"
            : "span_shipment.report_packing_list_picking";

        const recordId = this.state.selectedBatchId || this.state.selectedPickingId;
        const modelName = this.state.selectedBatchId ? "stock.picking.batch" : "stock.picking";

        await this.action.doAction({
            type: "ir.actions.report",
            report_name: reportName,
            report_type: "qweb-pdf",
            data: null,
            context: {
                active_ids: [recordId],
                active_model: modelName,
            },
        });
    }


    async closeCarriers() {
        // Open delivery orders list filtered for carrier closing
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Close Carriers - Select Delivery Orders",
            res_model: "stock.picking",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["picking_type_id.code", "=", "outgoing"],
                ["state", "=", "assigned"],
                ["carrier_id", "!=", false]
            ],
            context: {
                search_default_group_by_carrier: 1,
                create: false,
                edit: false,
            },
        });
    }

    // Integration Section

    async viewEDI856Logs() {
        // View EDI 856 logs (from truecommerce_edi module)
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "EDI 856 Logs",
            res_model: "edi.log",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            context: {},
        });
    }

    async generateEDI856() {
        // Generate EDI 856 files (from truecommerce_edi module)
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Generate EDI 856",
            res_model: "edi.manual.generate.wizard",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context: {},
        });
    }

    // Configuration Section

    async openGPConfiguration() {
        // Open GP configuration (from gp_integration module - under queue_job menu)
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "GP Configuration",
            res_model: "gp.config",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            context: {},
        });
    }

    async openEDISettings() {
        // Open EDI settings (from truecommerce_edi module)
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "EDI Settings",
            res_model: "edi.config",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            context: {},
        });
    }

    async openDeliveryMethods() {
        // Open delivery methods configuration
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Delivery Methods",
            res_model: "delivery.carrier",
            view_mode: "list,kanban,form",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            context: {},
        });
    }

    async openCustomers() {
        // Open customers list
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Customers",
            res_model: "res.partner",
            view_mode: "list,kanban,form",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            domain: [["is_company", "=", true]],
            context: {
                default_is_company: true,
                default_customer_rank: 1,
            },
        });
    }

    // Quick Actions

    async viewBatches() {
        // View existing batch pickings
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Batch Pickings",
            res_model: "stock.picking.batch",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            context: {},
        });
    }

    async viewPackages() {
        // View packages
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Packages",
            res_model: "stock.quant.package",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            context: {},
        });
    }
}

SpanShipmentOpeningScreen.template = "span_shipment.OpeningScreen";

// Register the component in the actions registry
registry.category("actions").add("span_shipment.opening_screen", SpanShipmentOpeningScreen);