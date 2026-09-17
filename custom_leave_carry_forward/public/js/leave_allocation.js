frappe.ui.form.on("Leave Allocation", {
    onload: function (frm) {
        setup_carry_forward_fields(frm);
    },

    onload_post_render: function (frm) {
        setup_carry_forward_fields(frm);

        // Default checkbox is already checked through Customize Form.
        // Trigger calculation immediately for a new allocation.
        if (
            frm.is_new() &&
            cint(frm.doc.carry_forward) === 1 &&
            frm.doc.leave_type &&
            frm.doc.employee
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
        if (cint(frm.doc.carry_forward) === 1) {
            frm.trigger("calculate_total_leaves_allocated");
        } else {
            frm.set_value(
                "unused_leaves",
                0
            );

            frm.set_value(
                "total_leaves_allocated",
                flt(frm.doc.new_leaves_allocated)
            );
        }
    },

    unused_leaves: function (frm) {
        frm.set_value(
            "total_leaves_allocated",
            flt(frm.doc.unused_leaves) +
            flt(frm.doc.new_leaves_allocated)
        );
    },

    calculate_total_leaves_allocated: function (frm) {
        if (
            cint(frm.doc.carry_forward) === 1 &&
            frm.doc.leave_type &&
            frm.doc.employee
        ) {
            frappe.call({
                method: "set_total_leaves_allocated",
                doc: frm.doc,
                freeze: false,
                callback: function (r) {
                    if (!r.exc) {
                        frm.refresh_field("unused_leaves");
                        frm.refresh_field("total_leaves_allocated");

                        show_carry_forward_fields(frm);
                    }
                }
            });
        } else {
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

    // Total Leaves Allocated should remain visible.
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
