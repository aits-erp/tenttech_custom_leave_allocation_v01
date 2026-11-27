from frappe.model.document import Document


class StockCategoryMapping(Document):
	"""Maps an Item Group (and its unmapped sub-groups) to a Stock Summary category."""
