package com.kav1.warehouse.ui

import android.content.Context
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.kav1.warehouse.R
import com.kav1.warehouse.data.local.WarehouseItemRow
import com.kav1.warehouse.data.local.WarehouseSummary
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.launch

/**
 * Warehouses, then what is in one of them shelf by shelf, for checking a
 * warehouse or counting its stock. Read-only: the split is set in the panel.
 */
class WarehousesActivity : AppCompatActivity() {

    private val selected = MutableStateFlow<String?>(null)
    private val query = MutableStateFlow("")
    private lateinit var header: TextView
    private lateinit var search: EditText
    private lateinit var empty: TextView
    private val warehouseAdapter = WarehouseAdapter()
    private val itemAdapter = ItemAdapter()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setTitle(R.string.warehouses_title)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        val pad = (12 * resources.displayMetrics.density).toInt()
        header = TextView(this).apply {
            textSize = 18f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            setTextColor(ContextCompat.getColor(context, R.color.primary))
            setPadding(0, 0, 0, pad / 2)
        }
        search = EditText(this).apply {
            setHint(R.string.warehouse_search_hint)
            setSingleLine(true)
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
                override fun afterTextChanged(s: Editable?) {
                    query.value = s?.toString().orEmpty()
                }
            })
        }
        empty = TextView(this).apply {
            textSize = 16f
            setTextColor(ContextCompat.getColor(context, R.color.text_secondary))
            setPadding(0, pad, 0, pad)
        }
        val list = ListView(this)
        list.setOnItemClickListener { _, _, position, _ ->
            if (selected.value == null) {
                selected.value = warehouseAdapter.rows[position].name
            } else {
                startActivity(ItemActivity.intent(this, itemAdapter.rows[position].qrId))
            }
        }
        setContentView(
            LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                layoutDirection = View.LAYOUT_DIRECTION_RTL
                setPadding(pad, pad, pad, pad)
                addView(header)
                addView(search)
                addView(empty)
                addView(list, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
            },
        )
        observe(list)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (selected.value != null) {
            selected.value = null
            search.setText("")
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    override fun onSupportNavigateUp(): Boolean {
        @Suppress("DEPRECATION")
        onBackPressed()
        return true
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    private fun observe(list: ListView) {
        val repo = app.repository
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    repo.observeWarehouses().collect { rows ->
                        warehouseAdapter.submit(rows)
                        if (selected.value == null) showWarehouses(list)
                    }
                }
                combine(selected, query) { wh, q -> wh to q }
                    .flatMapLatest { (wh, q) ->
                        if (wh == null) flowOf(null) else repo.observeWarehouseItems(wh, q)
                    }
                    .collect { rows ->
                        val wh = selected.value
                        if (rows == null || wh == null) {
                            showWarehouses(list)
                        } else {
                            itemAdapter.submit(rows)
                            list.adapter = itemAdapter
                            search.visibility = View.VISIBLE
                            header.text = getString(
                                R.string.warehouse_header,
                                wh,
                                rows.size,
                                rows.sumOf { it.quantity },
                            )
                            empty.setText(R.string.warehouse_items_empty)
                            empty.visibility = if (rows.isEmpty()) View.VISIBLE else View.GONE
                        }
                    }
            }
        }
    }

    private fun showWarehouses(list: ListView) {
        list.adapter = warehouseAdapter
        search.visibility = View.GONE
        header.setText(R.string.warehouses_pick)
        empty.setText(R.string.warehouses_empty)
        empty.visibility = if (warehouseAdapter.rows.isEmpty()) View.VISIBLE else View.GONE
    }

    private inner class WarehouseAdapter : BaseAdapter() {
        var rows: List<WarehouseSummary> = emptyList()
            private set

        fun submit(newRows: List<WarehouseSummary>) {
            rows = newRows
            notifyDataSetChanged()
        }

        override fun getCount() = rows.size
        override fun getItem(position: Int) = rows[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val view = convertView ?: LayoutInflater.from(parent.context).inflate(R.layout.row_item, parent, false)
            val row = rows[position]
            view.findViewById<TextView>(R.id.txtItemName).text = row.name
            view.findViewById<TextView>(R.id.txtItemStatus).text = row.units.toString()
            view.findViewById<TextView>(R.id.txtItemDetails).text =
                getString(R.string.warehouse_row, row.items, row.units)
            return view
        }
    }

    private inner class ItemAdapter : BaseAdapter() {
        var rows: List<WarehouseItemRow> = emptyList()
            private set

        fun submit(newRows: List<WarehouseItemRow>) {
            rows = newRows
            notifyDataSetChanged()
        }

        override fun getCount() = rows.size
        override fun getItem(position: Int) = rows[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val view = convertView ?: LayoutInflater.from(parent.context).inflate(R.layout.row_item, parent, false)
            val row = rows[position]
            val context: Context = parent.context
            view.findViewById<TextView>(R.id.txtItemName).text = row.name ?: row.qrId
            view.findViewById<TextView>(R.id.txtItemStatus).text = row.quantity.toString()
            view.findViewById<TextView>(R.id.txtItemDetails).text = listOfNotNull(
                if (row.shelf.isEmpty()) context.getString(R.string.shelf_none) else context.getString(R.string.label_shelf, row.shelf),
                context.categoryLabel(row.category),
                row.qrId,
            ).joinToString(" · ")
            return view
        }
    }
}
