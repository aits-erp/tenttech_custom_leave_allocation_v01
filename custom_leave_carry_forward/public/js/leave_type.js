// frappe.ui.form.on("Leave Type", {
//     refresh(frm) {
//         toggle_infinite_carry_forward_fields(frm);
//     },

//     custom_infinite_carry_forward(frm) {
//         toggle_infinite_carry_forward_fields(frm);
//     }
// });


// function toggle_infinite_carry_forward_fields(frm) {

//     const infinite = cint(
//         frm.doc.custom_infinite_carry_forward
//     );

//     if (infinite) {

//         // Infinite Carry Forward is enabled.
//         // From Date and To Date are not applicable.
//         frm.set_df_property(
//             "custom_carry_forward_from_date",
//             "hidden",
//             1
//         );

//         frm.set_df_property(
//             "custom_carry_forward_to_date",
//             "hidden",
//             1
//         );

//     } else {

//         // Normal period-based Carry Forward.
//         // Show From Date and To Date.
//         frm.set_df_property(
//             "custom_carry_forward_from_date",
//             "hidden",
//             0
//         );

//         frm.set_df_property(
//             "custom_carry_forward_to_date",
//             "hidden",
//             0
//         );
//     }
// }




frappe.ui.form.on("Leave Type", {

    refresh(frm) {
        toggle_carry_forward_fields(frm);
    },

    // Standard ERPNext field
    is_carry_forward(frm) {
        toggle_carry_forward_fields(frm);
    },

    // Custom Infinite Carry Forward field
    custom_infinite_carry_forward(frm) {
        toggle_carry_forward_fields(frm);
    }
});


function toggle_carry_forward_fields(frm) {

    const is_carry_forward = cint(
        frm.doc.is_carry_forward
    );

    const infinite = cint(
        frm.doc.custom_infinite_carry_forward
    );


    /*
     * CASE 1:
     * Is Carry Forward is NOT enabled.
     *
     * Custom carry-forward period fields
     * are not applicable.
     */
    if (!is_carry_forward) {

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

        frm.set_df_property(
            "custom_infinite_carry_forward",
            "hidden",
            1
        );

        return;
    }


    /*
     * CASE 2:
     * Is Carry Forward is enabled.
     *
     * Infinite Carry Forward is visible.
     */
    frm.set_df_property(
        "custom_infinite_carry_forward",
        "hidden",
        0
    );


    /*
     * CASE 3:
     * Is Carry Forward = Yes
     * Infinite Carry Forward = Yes
     *
     * From Date and To Date are not required.
     */
    if (infinite) {

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

    }

    /*
     * CASE 4:
     * Is Carry Forward = Yes
     * Infinite Carry Forward = No
     *
     * Show From Date and To Date.
     */
    else {

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