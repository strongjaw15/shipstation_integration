import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder

from shipstation_integration.orders import update_shipstation_order_status


class ShipStationSalesOrder(SalesOrder):
	def calculate_commission(self):
		commission_formula = frappe.get_cached_value(
			"Sales Partner", self.sales_partner, "commission_formula"
		)
		if not self.shipstation_order_id or not commission_formula:
			super().calculate_commission()
		elif self.shipstation_order_id and commission_formula:
			self.total_commission = get_formula_based_commission(self, commission_formula)

	def get_sss(self):
		sss_name = frappe.db.get_value(
			"Shipstation Store",
			{
				"store_name": self.shipstation_store_name,
				"marketplace_name": self.marketplace,
			},
			["parent"],
		)
		if sss_name:
			return frappe.get_doc("Shipstation Settings", sss_name)
		else:
			return None

	# synchronize status with shipstation
	def on_change(self):
		if (
			self.shipstation_order_id
			and self.has_value_changed("status")
			and self.status not in ["Draft", "Closed"]
		):
			sss = self.get_sss()
			if sss and sss.enabled and sss.sync_so_status:
				update_shipstation_order_status(
					settings=sss, order_id=self.shipstation_order_id, status=self.status
				)


def get_formula_based_commission(doc, commission_formula=None):
	if not commission_formula:
		commission_formula = frappe.get_cached_value(
			"Sales Partner", doc.sales_partner, "commission_formula"
		)

	eval_globals = frappe._dict(
		{
			"frappe": frappe._dict(
				{"get_value": frappe.db.get_value, "get_all": frappe.db.get_all}
			),
			"flt": frappe.utils.data.flt,
			"min": min,
			"max": max,
			"sum": sum,
		}
	)
	eval_locals = {
		"doc": doc,
	}

	try:
		return frappe.safe_eval(
			commission_formula, eval_globals=eval_globals, eval_locals=eval_locals
		)
	except Exception as e:
		print("Error evaluating commission formula:\n", e)
		e = f"{e}\n{doc.as_dict()}"
		frappe.log_error(
			title=f"Error evaluating commission formula for {doc.sales_partner or 'No Sales Partner'}",
			message=e,
		)
		return None


# flt((( doc.grand_total * 0.1325) * 0.9)  + 0.40, 2)
# flt(((
# 	(min(doc.total, 2500) * 0.1235) + (max(doc.total - 2500, 0) *.0235)
# ) * 0.9)  + 0.40, 2)
# sum([r.amount * .16 for r in doc.items if not r.is_free_item]) # 16% per item
