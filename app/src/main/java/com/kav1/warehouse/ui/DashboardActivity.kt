package com.kav1.warehouse.ui

import android.content.Context
import android.graphics.Typeface
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.kav1.warehouse.R
import com.kav1.warehouse.data.local.CategorySummary
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.ItemWithHolder
import com.kav1.warehouse.databinding.ActivityDashboardBinding
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.launch

/**
 * Inventory overview: counts per status, a searchable list with holders, and
 * a per-type summary (units per status against the target quantity).
 */
class DashboardActivity : AppCompatActivity() {

    private lateinit var binding: ActivityDashboardBinding
    private val statusFilter = MutableStateFlow<String?>(null)
    private val typeFilter = MutableStateFlow<String?>(null)
    private val showTypes = MutableStateFlow(false)
    private val query = MutableStateFlow("")
    private lateinit var adapter: ItemAdapter
    private lateinit var typeAdapter: TypeAdapter

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityDashboardBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setTitle(R.string.dashboard_title)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        adapter = ItemAdapter(this)
        binding.listItems.adapter = adapter
        binding.listItems.setOnItemClickListener { _, _, position, _ ->
            startActivity(ItemActivity.intent(this, adapter.getItem(position).qrId))
        }

        typeAdapter = TypeAdapter(this)
        binding.listTypes.adapter = typeAdapter
        binding.listTypes.setOnItemClickListener { _, _, position, _ ->
            typeFilter.value = typeAdapter.getItem(position).name
            showTypes.value = false
        }
        binding.btnModeItems.setOnClickListener { showTypes.value = false }
        binding.btnModeTypes.setOnClickListener { showTypes.value = true }
        binding.txtFilter.setOnClickListener { typeFilter.value = null }

        binding.tileTotal.setOnClickListener { statusFilter.value = null }
        binding.tileAvailable.setOnClickListener { statusFilter.value = ItemStatus.AVAILABLE }
        binding.tileBorrowed.setOnClickListener { statusFilter.value = ItemStatus.BORROWED }
        binding.tileIssued.setOnClickListener { statusFilter.value = ItemStatus.ISSUED }
        binding.editSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                query.value = s?.toString().orEmpty()
            }
        })

        observe()
    }

    override fun onSupportNavigateUp(): Boolean {
        finish()
        return true
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    private fun observe() {
        val repo = app.repository
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    // Units, not item rows: one QR can stock many.
                    repo.observeUnitTotals().collect { totals ->
                        binding.countTotal.text = totals.total.toString()
                        binding.countAvailable.text = totals.available.toString()
                        binding.countBorrowed.text = totals.borrowed.toString()
                        binding.countIssued.text = totals.issued.toString()
                    }
                }
                launch {
                    combine(statusFilter, typeFilter) { status, type -> status to type }.collect { (status, type) ->
                        binding.txtFilter.text = when {
                            type != null -> getString(R.string.dashboard_filter_type, categoryLabel(type))
                            status == null -> getString(R.string.dashboard_filter_all)
                            else -> getString(R.string.dashboard_filter, statusLabel(status))
                        }
                    }
                }
                launch {
                    showTypes.collect { types ->
                        binding.listTypes.visibility = if (types) View.VISIBLE else View.GONE
                        binding.listItems.visibility = if (types) View.GONE else View.VISIBLE
                        binding.editSearch.visibility = if (types) View.GONE else View.VISIBLE
                        binding.txtFilter.visibility = if (types) View.GONE else View.VISIBLE
                        highlight(binding.btnModeTypes, types)
                        highlight(binding.btnModeItems, !types)
                        updateEmpty()
                    }
                }
                launch {
                    repo.observeCategorySummaries().collect {
                        typeAdapter.submit(it)
                        updateEmpty()
                    }
                }
                combine(statusFilter, query, typeFilter) { status, q, type -> Triple(status, q, type) }
                    .flatMapLatest { (status, q, type) -> repo.observeItems(status, q, type) }
                    .collect { items ->
                        adapter.submit(items)
                        updateEmpty()
                    }
            }
        }
    }

    private fun updateEmpty() {
        val types = showTypes.value
        val empty = if (types) typeAdapter.count == 0 else adapter.count == 0
        binding.txtEmpty.setText(if (types) R.string.types_empty else R.string.dashboard_empty)
        binding.txtEmpty.visibility = if (empty) View.VISIBLE else View.GONE
    }

    private fun highlight(button: TextView, selected: Boolean) {
        button.setTextColor(
            ContextCompat.getColor(this, if (selected) R.color.primary else R.color.text_secondary),
        )
        button.setTypeface(null, if (selected) Typeface.BOLD else Typeface.NORMAL)
    }

    private class TypeAdapter(private val context: Context) : BaseAdapter() {
        private var rows: List<CategorySummary> = emptyList()

        fun submit(newRows: List<CategorySummary>) {
            rows = newRows
            notifyDataSetChanged()
        }

        override fun getCount() = rows.size
        override fun getItem(position: Int) = rows[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val row = convertView
                ?: LayoutInflater.from(context).inflate(R.layout.row_item, parent, false)
            val type = rows[position]
            row.findViewById<TextView>(R.id.txtItemName).text = context.categoryLabel(type.name)
            val missing = type.missing
            row.findViewById<TextView>(R.id.txtItemStatus).apply {
                text = when {
                    missing == null -> ""
                    missing > 0 -> context.getString(R.string.type_row_missing, missing)
                    else -> context.getString(R.string.type_row_full)
                }
                setTextColor(
                    ContextCompat.getColor(context, if (missing != null && missing > 0) R.color.borrow else R.color.return_green),
                )
            }
            var details = context.getString(
                R.string.type_row_counts,
                type.total,
                type.available,
                type.borrowed,
                type.issued,
            )
            type.targetQty?.let { details = context.getString(R.string.type_row_target, it) + " · " + details }
            row.findViewById<TextView>(R.id.txtItemDetails).text = details
            return row
        }
    }

    private class ItemAdapter(private val context: Context) : BaseAdapter() {
        private var items: List<ItemWithHolder> = emptyList()

        fun submit(newItems: List<ItemWithHolder>) {
            items = newItems
            notifyDataSetChanged()
        }

        override fun getCount() = items.size
        override fun getItem(position: Int) = items[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val row = convertView
                ?: LayoutInflater.from(context).inflate(R.layout.row_item, parent, false)
            val item = items[position]
            row.findViewById<TextView>(R.id.txtItemName).text =
                if (item.category.isNotEmpty() && item.category != item.name) {
                    "${item.name} (${item.category})"
                } else {
                    item.name
                }
            row.findViewById<TextView>(R.id.txtItemStatus).apply {
                text = context.statusLabel(item.currentStatus)
                setTextColor(context.statusColor(item.currentStatus))
            }
            val lastAction = item.lastActionAt?.let { context.formatDateTime(it) } ?: ""
            val details = if (item.quantity > 1) {
                context.getString(R.string.dashboard_row_stock, item.qrId, item.availableQty, item.quantity)
            } else if (item.holderUserId != null) {
                context.getString(
                    R.string.dashboard_row_holder,
                    item.holderName ?: item.holderUserId,
                    item.holderUnit.orEmpty(),
                    lastAction,
                )
            } else {
                context.getString(R.string.dashboard_row_details, item.qrId, lastAction)
            }
            row.findViewById<TextView>(R.id.txtItemDetails).text = details
            return row
        }
    }
}
