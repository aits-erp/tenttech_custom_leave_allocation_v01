frappe.ui.form.on("Leave Type", {
    refresh(frm) {
        toggle_infinite_carry_forward_fields(frm);
    },

    custom_infinite_carry_forward(frm) {
        toggle_infinite_carry_forward_fields(frm);
    }
});


function toggle_infinite_carry_forward_fields(frm) {

    const infinite = cint(
        frm.doc.custom_infinite_carry_forward
    );

    if (infinite) {

        // Infinite Carry Forward is enabled.
        // From Date and To Date are not applicable.
        frm.set_df_property(
            "custom_carry_forward_from_date",
            "hidden",
            1
        );

        frm.set_df_property(
            "custom_carry_forward_to_date",
            "hidden",
            1
        );

    } else {

        // Normal period-based Carry Forward.
        // Show From Date and To Date.
        frm.set_df_property(
            "custom_carry_forward_from_date",
            "hidden",
            0
        );

        frm.set_df_property(
            "custom_carry_forward_to_date",
            "hidden",
            0
        );
    }
}
