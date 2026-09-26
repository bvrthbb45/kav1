package com.kav1.warehouse.ui

import android.content.Context
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.kav1.warehouse.R
import com.kav1.warehouse.data.local.ItemStatus
import com.kav1.warehouse.data.local.ItemWithHolder
import com.kav1.warehouse.databinding.ActivityDashboardBinding
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.launch

/** Inventory overview: counts per status and a searchable list with holders. */
class DashboardActivity : AppCompatActivity() {

    private lateinit var binding: ActivityDashboardBinding
    private val statusFilter = MutableStateFlow<String?>(null)
    private val query = MutableStateFlow("")
    private lateinit var adapter: ItemAdapter

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
                    repo.observeStatusCounts().collect { counts ->
                        val byStatus = counts.associate { it.status to it.count }
                        binding.countTotal.text = counts.sumOf { it.count }.toString()
                        binding.countAvailable.text = (byStatus[ItemStatus.AVAILABLE] ?: 0).toString()
                        binding.countBorrowed.text = (byStatus[ItemStatus.BORROWED] ?: 0).toString()
                        binding.countIssued.text = (byStatus[ItemStatus.ISSUED] ?: 0).toString()
                    }
                }
                launch {
                    statusFilter.collect { status ->
                        binding.txtFilter.text = if (status == null) {
                            getString(R.string.dashboard_filter_all)
                        } else {
                            getString(R.string.dashboard_filter, statusLabel(status))
                        }
                    }
                }
                combine(statusFilter, query) { status, q -> status to q }
                    .flatMapLatest { (status, q) -> repo.observeItems(status, q) }
                    .collect { items ->
                        adapter.submit(items)
                        binding.txtEmpty.visibility = if (items.isEmpty()) View.VISIBLE else View.GONE
                    }
            }
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
            row.findViewById<TextView>(R.id.txtItemName).text = item.name
            row.findViewById<TextView>(R.id.txtItemStatus).apply {
                text = context.statusLabel(item.currentStatus)
                setTextColor(context.statusColor(item.currentStatus))
            }
            val lastAction = item.lastActionAt?.let { context.formatDateTime(it) } ?: ""
            val details = if (item.holderUserId != null) {
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
