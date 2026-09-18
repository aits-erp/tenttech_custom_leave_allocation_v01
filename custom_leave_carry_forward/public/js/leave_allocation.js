frappe.ui.form.on("Leave Allocation", {

    onload: function (frm) {
        setup_carry_forward_fields(frm);
    },

    onload_post_render: function (frm) {
        setup_carry_forward_fields(frm);

        // For a new document, calculate only when
        // the required fields are already available.
        // This calculation does NOT validate or save.
        if (
            frm.is_new() &&
            cint(frm.doc.carry_forward) === 1 &&
            frm.doc.leave_type &&
            frm.doc.employee &&
            frm.doc.from_date
        ) {
            frm.trigger("calculate_total_leaves_allocated");
        }
    },

    refresh: function (frm) {
        setup_carry_forward_fields(frm);
    },

    employee: function (frm) {
        frm.trigger("calculate_total_leaves_allocated");
    },

    leave_type: function (frm) {
        frm.trigger("calculate_total_leaves_allocated");
    },

    from_date: function (frm) {
        frm.trigger("calculate_total_leaves_allocated");
    },

    to_date: function (frm) {
        frm.trigger("calculate_total_leaves_allocated");
    },

    carry_forward: function (frm) {
        setup_carry_forward_fields(frm);

        frm.trigger("calculate_total_leaves_allocated");
    },

    new_leaves_allocated: function (frm) {
        frm.trigger("calculate_total_leaves_allocated");
    },

    calculate_total_leaves_allocated: function (frm) {

        /*
         * IMPORTANT:
         *
         * This is ONLY a calculation.
         * It must NOT:
         * - validate the document
         * - save the document
         * - submit the document
         * - show the "Total leaves allocated is mandatory" message
         */

        if (
            cint(frm.doc.carry_forward) === 1 &&
            frm.doc.leave_type &&
            frm.doc.employee &&
            frm.doc.from_date
        ) {

            frappe.call({
                method: "set_total_leaves_allocated",
                doc: frm.doc,
                freeze: false,

                callback: function (r) {

                    if (r.exc) {
                        return;
                    }

                    frm.refresh_field("unused_leaves");
                    frm.refresh_field("total_leaves_allocated");

                    show_carry_forward_fields(frm);
                }
            });

        } else {

            // No carry forward selected.
            frm.set_value("unused_leaves", 0);

            frm.set_value(
                "total_leaves_allocated",
                flt(frm.doc.new_leaves_allocated)
            );

            hide_carry_forward_fields(frm);
        }
    }
});


function setup_carry_forward_fields(frm) {

    if (cint(frm.doc.carry_forward) === 1) {
        show_carry_forward_fields(frm);
    } else {
        hide_carry_forward_fields(frm);
    }
}


function show_carry_forward_fields(frm) {

    frm.set_df_property(
        "unused_leaves",
        "hidden",
        0
    );

    frm.set_df_property(
        "total_leaves_allocated",
        "hidden",
        0
    );

    frm.toggle_display(
        "unused_leaves",
        true
    );

    frm.toggle_display(
        "total_leaves_allocated",
        true
    );
}


function hide_carry_forward_fields(frm) {

    frm.set_df_property(
        "unused_leaves",
        "hidden",
        1
    );

    frm.toggle_display(
        "unused_leaves",
        false
    );

    // Total Leaves Allocated remains visible.
    frm.set_df_property(
        "total_leaves_allocated",
        "hidden",
        0
    );

    frm.toggle_display(
        "total_leaves_allocated",
        true
    );
}