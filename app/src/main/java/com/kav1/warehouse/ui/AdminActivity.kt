package com.kav1.warehouse.ui

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.BaseAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import com.kav1.warehouse.BuildConfig
import com.kav1.warehouse.R
import com.kav1.warehouse.data.remote.ApiClient
import com.kav1.warehouse.databinding.ActivityAdminBinding
import com.kav1.warehouse.domain.sync.SyncScheduler
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

/**
 * Management screen (PIN protected): add/edit items and users, and device
 * settings. Edits are saved locally and uploaded on the next sync.
 */
class AdminActivity : AppCompatActivity() {

    private lateinit var binding: ActivityAdminBinding
    private val showUsers = MutableStateFlow(false)
    private val query = MutableStateFlow("")
    private lateinit var adapter: RowAdapter

    private val scanLauncher = registerForActivityResult(ScanContract()) { result ->
        val code = result.contents?.trim()
        if (!code.isNullOrEmpty()) openItemEditor(code)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityAdminBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setTitle(R.string.admin_title)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        adapter = RowAdapter(this)
        binding.listRows.adapter = adapter
        binding.listRows.setOnItemClickListener { _, _, position, _ ->
            val row = adapter.getItem(position)
            if (row.isUser) {
                showUserDialog(row.id, row.title, row.unit)
            } else {
                showItemDialog(row.id, row.title)
            }
        }

        binding.btnScanNewItem.setOnClickListener {
            scanLauncher.launch(
                ScanOptions()
                    .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                    .setPrompt(getString(R.string.scan_prompt))
                    .setBeepEnabled(true)
                    .setOrientationLocked(true),
            )
        }
        binding.btnAddItem.setOnClickListener { showItemDialog(null, null) }
        binding.btnAddUser.setOnClickListener { showUserDialog(null, null, null) }
        binding.btnTabItems.setOnClickListener { showUsers.value = false }
        binding.btnTabUsers.setOnClickListener { showUsers.value = true }
        binding.btnServerUrl.setOnClickListener { showServerUrlDialog() }
        binding.btnChangePin.setOnClickListener { showChangePinDialog() }
        binding.editSearch.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit
            override fun afterTextChanged(s: Editable?) {
                query.value = s?.toString().orEmpty()
            }
        })

        observe()

        if (savedInstanceState == null) {
            intent.getStringExtra(EXTRA_NEW_ITEM_QR)?.let { openItemEditor(it) }
        }
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
                    showUsers.collect { users ->
                        highlightTab(binding.btnTabUsers, users)
                        highlightTab(binding.btnTabItems, !users)
                    }
                }
                combine(showUsers, query) { users, q -> users to q }
                    .flatMapLatest { (users, q) -> if (users) userRows(q) else itemRows(q) }
                    .collect { adapter.submit(it) }
            }
        }
    }

    private fun itemRows(q: String): Flow<List<Row>> =
        app.repository.observeItems(null, q).map { items ->
            items.map {
                Row(
                    id = it.qrId,
                    title = it.name,
                    subtitle = "${it.qrId} · ${statusLabel(it.currentStatus)}",
                    unit = null,
                    pending = it.pendingUpload,
                    isUser = false,
                )
            }
        }

    private fun userRows(q: String): Flow<List<Row>> =
        app.repository.observeUsers(q).map { users ->
            users.map {
                Row(
                    id = it.userId,
                    title = it.fullName,
                    subtitle = getString(R.string.user_row_details, it.userId, it.unit),
                    unit = it.unit,
                    pending = it.pendingUpload,
                    isUser = true,
                )
            }
        }

    private fun highlightTab(button: TextView, selected: Boolean) {
        button.setTextColor(
            ContextCompat.getColor(this, if (selected) R.color.primary else R.color.text_secondary),
        )
        button.setTypeface(null, if (selected) android.graphics.Typeface.BOLD else android.graphics.Typeface.NORMAL)
    }

    // --- Items ---

    /** New code: add dialog; known code: edit dialog. */
    private fun openItemEditor(qrId: String) {
        lifecycleScope.launch {
            val existing = app.repository.getItem(qrId)
            if (existing != null) {
                toast(R.string.item_exists_editing)
                showItemDialog(existing.qrId, existing.name)
            } else {
                showItemDialog(null, null, prefilledQr = qrId)
            }
        }
    }

    private fun showItemDialog(qrId: String?, name: String?, prefilledQr: String? = null) {
        val form = Form(this)
        val qrField = form.field(R.string.item_code_hint, qrId ?: prefilledQr, enabled = qrId == null)
        val nameField = form.field(R.string.item_name_hint, name)
        form.show(if (qrId == null) R.string.item_dialog_add else R.string.item_dialog_edit) {
            val code = form.value(qrField, MAX_QR) ?: return@show false
            val itemName = form.value(nameField, MAX_NAME) ?: return@show false
            lifecycleScope.launch {
                if (qrId == null && app.repository.getItem(code) != null) {
                    toast(R.string.item_exists_editing)
                }
                app.repository.saveItem(code, itemName)
                savedPendingSync()
            }
            true
        }
    }

    // --- Users ---

    private fun showUserDialog(userId: String?, fullName: String?, unit: String?) {
        val form = Form(this)
        val idField = form.field(R.string.user_id_hint, userId, enabled = userId == null)
        val nameField = form.field(R.string.user_name_hint, fullName)
        val unitField = form.field(R.string.user_unit_hint, unit)
        form.show(if (userId == null) R.string.user_dialog_add else R.string.user_dialog_edit) {
            val id = form.value(idField, MAX_USER_ID) ?: return@show false
            val name = form.value(nameField, MAX_NAME) ?: return@show false
            val userUnit = form.value(unitField, MAX_NAME, required = false) ?: return@show false
            lifecycleScope.launch {
                app.repository.saveUser(id, name, userUnit)
                savedPendingSync()
            }
            true
        }
    }

    private fun savedPendingSync() {
        toast(R.string.saved_pending_sync)
        SyncScheduler.requestSoon(applicationContext)
    }

    // --- Settings ---

    private fun showServerUrlDialog() {
        val (view, edit) = dialogEditText(
            R.string.server_url_hint,
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI,
        )
        edit.setText(app.prefs.serverUrl)
        edit.textDirection = View.TEXT_DIRECTION_LTR
        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.admin_server_url)
            .setView(view)
            .setPositiveButton(R.string.btn_confirm, null)
            .setNeutralButton(R.string.btn_default) { _, _ ->
                app.prefs.serverUrl = BuildConfig.SERVER_BASE_URL
                toast(R.string.server_url_saved)
            }
            .setNegativeButton(R.string.btn_cancel, null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val url = ApiClient.normalizeBaseUrl(edit.text.toString())
                if (url == null) {
                    edit.error = getString(R.string.server_url_invalid)
                } else {
                    app.prefs.serverUrl = url
                    toast(R.string.server_url_saved)
                    dialog.dismiss()
                }
            }
        }
        dialog.show()
    }

    private fun showChangePinDialog() {
        val (view, edit) = dialogEditText(
            R.string.new_pin_hint,
            InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD,
        )
        val dialog = AlertDialog.Builder(this)
            .setTitle(R.string.admin_change_pin)
            .setView(view)
            .setPositiveButton(R.string.btn_confirm, null)
            .setNegativeButton(R.string.btn_cancel, null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val pin = edit.text.toString()
                if (pin.length < 4) {
                    edit.error = getString(R.string.new_pin_short)
                } else {
                    app.prefs.adminPin = pin
                    toast(R.string.pin_changed)
                    dialog.dismiss()
                }
            }
        }
        dialog.show()
    }

    // --- Helpers ---

    private data class Row(
        val id: String,
        val title: String,
        val subtitle: String,
        val unit: String?,
        val pending: Boolean,
        val isUser: Boolean,
    )

    /** A small vertical form inside an AlertDialog that stays open until valid. */
    private class Form(private val context: Context) {
        private val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (20 * context.resources.displayMetrics.density).toInt()
            setPadding(pad, pad / 2, pad, 0)
        }

        fun field(hint: Int, value: String?, enabled: Boolean = true): EditText =
            EditText(context).apply {
                setHint(hint)
                setSingleLine(true)
                setText(value.orEmpty())
                isEnabled = enabled
                layout.addView(this)
            }

        /** Trimmed value, or null (with an error shown) if invalid. */
        fun value(field: EditText, maxLength: Int, required: Boolean = true): String? {
            val text = field.text.toString().trim()
            return when {
                required && text.isEmpty() -> {
                    field.error = context.getString(R.string.error_required)
                    null
                }
                text.length > maxLength -> {
                    field.error = context.getString(R.string.error_too_long, maxLength)
                    null
                }
                else -> text
            }
        }

        /** [onSave] returns true to close the dialog. */
        fun show(title: Int, onSave: () -> Boolean) {
            val dialog = AlertDialog.Builder(context)
                .setTitle(title)
                .setView(layout)
                .setPositiveButton(R.string.btn_confirm, null)
                .setNegativeButton(R.string.btn_cancel, null)
                .create()
            dialog.setOnShowListener {
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                    if (onSave()) dialog.dismiss()
                }
            }
            dialog.show()
        }
    }

    private class RowAdapter(private val context: Context) : BaseAdapter() {
        private var rows: List<Row> = emptyList()

        fun submit(newRows: List<Row>) {
            rows = newRows
            notifyDataSetChanged()
        }

        override fun getCount() = rows.size
        override fun getItem(position: Int) = rows[position]
        override fun getItemId(position: Int) = position.toLong()

        override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
            val view = convertView
                ?: LayoutInflater.from(context).inflate(R.layout.row_user, parent, false)
            val row = rows[position]
            view.findViewById<TextView>(R.id.txtUserName).text = row.title
            view.findViewById<TextView>(R.id.txtUserDetails).text =
                if (row.pending) {
                    "${row.subtitle} · ${context.getString(R.string.admin_pending_mark)}"
                } else {
                    row.subtitle
                }
            return view
        }
    }

    companion object {
        // Server-side limits (server/app/schemas.py).
        private const val MAX_QR = 128
        private const val MAX_USER_ID = 64
        private const val MAX_NAME = 200
        private const val EXTRA_NEW_ITEM_QR = "new_item_qr"

        /** Opens the management screen straight into "add item" for [qrId]. */
        fun newItemIntent(context: Context, qrId: String): Intent =
            Intent(context, AdminActivity::class.java).putExtra(EXTRA_NEW_ITEM_QR, qrId)
    }
}
