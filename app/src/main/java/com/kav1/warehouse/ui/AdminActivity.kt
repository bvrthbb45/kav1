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
import android.widget.ArrayAdapter
import android.widget.AutoCompleteTextView
import android.widget.BaseAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.RadioButton
import android.widget.RadioGroup
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
import com.kav1.warehouse.data.local.ItemKind
import com.kav1.warehouse.data.remote.ApiClient
import com.kav1.warehouse.databinding.ActivityAdminBinding
import com.kav1.warehouse.domain.sync.SyncScheduler
import com.kav1.warehouse.domain.sync.UsbLink
import kotlinx.coroutines.CancellationException
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
                lifecycleScope.launch {
                    app.repository.getItem(row.id)?.let {
                        showItemDialog(it.qrId, it.name, it.category, it.quantity, it.kind)
                    }
                }
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
        binding.btnTestConnection.setOnClickListener { testConnection() }
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
                    subtitle = if (it.quantity > 1 || it.kind == ItemKind.CONSUMABLE) {
                        getString(
                            R.string.dashboard_row_stock,
                            "${kindLabel(it.kind)} · ${categoryLabel(it.category)} · ${it.qrId}",
                            it.availableQty,
                            it.quantity,
                        )
                    } else {
                        "${categoryLabel(it.category)} · ${it.qrId} · ${itemStatusLabel(it.kind, it.currentStatus)}"
                    },
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
                showItemDialog(existing.qrId, existing.name, existing.category, existing.quantity, existing.kind)
            } else {
                showItemDialog(null, null, prefilledQr = qrId)
            }
        }
    }

    private fun showItemDialog(
        qrId: String?,
        name: String?,
        category: String? = null,
        quantity: Int = 1,
        kind: String = ItemKind.LOAN,
        prefilledQr: String? = null,
    ) {
        lifecycleScope.launch {
            val types = app.repository.getCategoryNames()
            val form = Form(this@AdminActivity)
            // Editable when editing too: changing it changes the item's serial.
            val qrField = form.field(R.string.item_code_hint, qrId ?: prefilledQr).apply {
                textDirection = View.TEXT_DIRECTION_LTR
            }
            val typeField = form.autocomplete(R.string.item_category_hint, category, types)
            val nameField = form.field(R.string.item_name_optional_hint, name)
            val kindField = form.choice(
                listOf(ItemKind.LOAN to R.string.kind_loan_long, ItemKind.CONSUMABLE to R.string.kind_consumable_long),
                kind,
            )
            val qtyField = form.field(R.string.item_quantity_hint, quantity.toString()).apply {
                inputType = InputType.TYPE_CLASS_NUMBER
            }
            val onDelete = qrId?.let { id -> { confirmDeleteItem(id, name.orEmpty()) } }
            form.show(if (qrId == null) R.string.item_dialog_add else R.string.item_dialog_edit, onDelete) {
                val code = form.value(qrField, MAX_QR) ?: return@show false
                val type = form.value(typeField, MAX_NAME, required = false) ?: return@show false
                val itemName = form.value(nameField, MAX_NAME, required = false) ?: return@show false
                if (itemName.isEmpty() && type.isEmpty()) {
                    nameField.error = getString(R.string.item_name_or_type_required)
                    return@show false
                }
                val qty = qtyField.text.toString().trim().toIntOrNull()
                if (qty == null || qty < 0 || qty > 1_000_000) {
                    qtyField.error = getString(R.string.quantity_invalid)
                    return@show false
                }
                val itemKind = kindField()
                lifecycleScope.launch {
                    val repo = app.repository
                    if (qrId != null && code != qrId) {
                        if (!repo.isItemIdFree(code, qrId)) {
                            toast(getString(R.string.item_id_taken, code))
                            return@launch
                        }
                        repo.renameItem(qrId, code)
                        toast(getString(R.string.item_id_changed, code))
                    } else if (qrId == null && repo.getItem(code) != null) {
                        toast(R.string.item_exists_editing)
                    }
                    repo.saveItem(code, itemName.ifEmpty { type }, type, qty, itemKind)
                    savedPendingSync()
                }
                true
            }
        }
    }

    private fun confirmDeleteItem(qrId: String, name: String) {
        AlertDialog.Builder(this)
            .setTitle(R.string.item_delete_title)
            .setMessage(getString(R.string.item_delete_confirm, name, qrId))
            .setPositiveButton(R.string.btn_delete) { _, _ ->
                lifecycleScope.launch {
                    app.repository.deleteItem(qrId)
                    deletedPendingSync()
                }
            }
            .setNegativeButton(R.string.btn_cancel, null)
            .show()
    }

    // --- Users ---

    private fun showUserDialog(userId: String?, fullName: String?, unit: String?) {
        val form = Form(this)
        // Editable when editing too: changing it changes the personal number.
        val idField = form.field(R.string.user_id_hint, userId).apply {
            textDirection = View.TEXT_DIRECTION_LTR
        }
        val nameField = form.field(R.string.user_name_hint, fullName)
        val unitField = form.field(R.string.user_unit_hint, unit)
        val onDelete = userId?.let { id -> { confirmDeleteUser(id, fullName.orEmpty()) } }
        form.show(if (userId == null) R.string.user_dialog_add else R.string.user_dialog_edit, onDelete) {
            val id = form.value(idField, MAX_USER_ID) ?: return@show false
            val name = form.value(nameField, MAX_NAME) ?: return@show false
            val userUnit = form.value(unitField, MAX_NAME, required = false) ?: return@show false
            lifecycleScope.launch {
                val repo = app.repository
                if (userId != null && id != userId) {
                    if (!repo.isUserIdFree(id, userId)) {
                        toast(getString(R.string.user_id_taken, id))
                        return@launch
                    }
                    repo.renameUser(userId, id)
                    toast(getString(R.string.user_id_changed, id))
                }
                repo.saveUser(id, name, userUnit)
                savedPendingSync()
            }
            true
        }
    }

    private fun confirmDeleteUser(userId: String, name: String) {
        AlertDialog.Builder(this)
            .setTitle(R.string.user_delete_title)
            .setMessage(getString(R.string.user_delete_confirm, name, userId))
            .setPositiveButton(R.string.btn_delete) { _, _ ->
                lifecycleScope.launch {
                    app.repository.deleteUser(userId)
                    deletedPendingSync()
                }
            }
            .setNegativeButton(R.string.btn_cancel, null)
            .show()
    }

    private fun deletedPendingSync() {
        toast(R.string.deleted_pending_sync)
        SyncScheduler.requestSoon(applicationContext)
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

    /** Calls /api/health on the configured server and shows exactly what happened. */
    private fun testConnection() {
        val url = app.prefs.serverUrl
        binding.btnTestConnection.isEnabled = false
        binding.btnTestConnection.text = getString(R.string.connection_testing, url)
        lifecycleScope.launch {
            // Wired sync does not use the network address at all, so check the cable first.
            val link = UsbLink.status(this@AdminActivity)
            val lastUsb = app.prefs.lastUsbSync
            val usbLine = if (link.serverSeen()) {
                getString(
                    R.string.connection_usb_ok,
                    if (lastUsb == 0L) getString(R.string.usb_never_synced) else formatDateTime(lastUsb),
                )
            } else {
                getString(R.string.connection_usb_none)
            }
            val message = try {
                val response = app.api().health()
                if (response.isSuccessful) {
                    getString(R.string.connection_ok, url, response.body()?.message.orEmpty()) + "\n\n" + usbLine
                } else {
                    usbLine + "\n\n" + getString(R.string.connection_http_error, url, response.code())
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                if (link.serverSeen()) {
                    usbLine + "\n\n" + getString(R.string.connection_network_not_needed, url)
                } else {
                    usbLine + "\n\n" +
                        getString(R.string.connection_failed, url, "${e.javaClass.simpleName}: ${e.message.orEmpty()}")
                }
            }
            binding.btnTestConnection.isEnabled = true
            binding.btnTestConnection.setText(R.string.admin_test_connection)
            AlertDialog.Builder(this@AdminActivity)
                .setTitle(R.string.admin_test_connection)
                .setMessage(message)
                .setPositiveButton(R.string.btn_close, null)
                .show()
        }
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
        private val container = LinearLayout(context).apply {
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
                container.addView(this)
            }

        /** Radio buttons; returns a getter for the selected key. */
        fun choice(options: List<Pair<String, Int>>, selected: String): () -> String {
            val group = RadioGroup(context).apply { orientation = RadioGroup.VERTICAL }
            val ids = options.map { (key, label) ->
                val button = RadioButton(context).apply {
                    id = View.generateViewId()
                    setText(label)
                }
                group.addView(button)
                if (key == selected) group.check(button.id)
                button.id to key
            }.toMap()
            container.addView(group)
            return { ids[group.checkedRadioButtonId] ?: options.first().first }
        }

        /** A field that suggests [suggestions] while typing. */
        fun autocomplete(hint: Int, value: String?, suggestions: List<String>): EditText =
            AutoCompleteTextView(context).apply {
                setHint(hint)
                setSingleLine(true)
                setText(value.orEmpty())
                threshold = 1
                setAdapter(ArrayAdapter(context, android.R.layout.simple_dropdown_item_1line, suggestions))
                container.addView(this)
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

        /** [onSave] returns true to close the dialog; [onDelete] adds a delete button. */
        fun show(title: Int, onDelete: (() -> Unit)? = null, onSave: () -> Boolean) {
            val builder = AlertDialog.Builder(context)
                .setTitle(title)
                .setView(container)
                .setPositiveButton(R.string.btn_confirm, null)
                .setNegativeButton(R.string.btn_cancel, null)
            if (onDelete != null) builder.setNeutralButton(R.string.btn_delete) { _, _ -> onDelete() }
            val dialog = builder.create()
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
