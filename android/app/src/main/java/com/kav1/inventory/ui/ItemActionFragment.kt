package com.kav1.inventory.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.core.os.bundleOf
import androidx.core.view.isVisible
import androidx.core.widget.doAfterTextChanged
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.kav1.inventory.R
import com.kav1.inventory.data.local.ActionType
import com.kav1.inventory.data.local.ItemStatus
import com.kav1.inventory.data.local.User
import com.kav1.inventory.databinding.FragmentItemActionBinding
import kotlinx.coroutines.launch

/** Shows a scanned item and records a Borrow/Return for a chosen user. */
class ItemActionFragment : Fragment() {

    private var _binding: FragmentItemActionBinding? = null
    private val binding get() = _binding!!

    private val viewModel: ItemActionViewModel by viewModels()

    private var users: List<User> = emptyList()
    private var selectedUser: User? = null
    private var actionPreselected = false

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        _binding = FragmentItemActionBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        binding.qrIdText.text = getString(R.string.qr_id_format, viewModel.qrId)
        actionPreselected = savedInstanceState != null

        binding.userInput.setOnItemClickListener { parent, _, position, _ ->
            val name = parent.getItemAtPosition(position) as String
            selectedUser = users.firstOrNull { it.name == name }
            binding.userInputLayout.error = null
            updateSaveEnabled()
        }
        binding.userInput.doAfterTextChanged { text ->
            // Typing over a picked name invalidates the selection until a user is picked again.
            if (selectedUser != null && text?.toString() != selectedUser?.name) {
                selectedUser = null
                updateSaveEnabled()
            }
        }
        binding.actionToggle.addOnButtonCheckedListener { _, _, _ -> updateSaveEnabled() }
        binding.saveButton.setOnClickListener { onSave() }
        binding.cancelButton.setOnClickListener { parentFragmentManager.popBackStack() }

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                launch {
                    viewModel.item.collect { item ->
                        binding.itemName.text = item?.name ?: getString(R.string.unknown_item)
                        binding.itemStatus.text = item?.status ?: getString(R.string.status_unknown)
                        binding.unknownItemWarning.isVisible = item == null
                        if (item != null && !actionPreselected) {
                            actionPreselected = true
                            binding.actionToggle.check(
                                if (item.status == ItemStatus.BORROWED) R.id.returnButton else R.id.borrowButton,
                            )
                        }
                    }
                }
                launch {
                    viewModel.users.collect { list ->
                        // Names are used as dropdown labels; disambiguate duplicates with the id.
                        val duplicates = list.groupingBy { it.name }.eachCount().filterValues { it > 1 }.keys
                        users = list.map { if (it.name in duplicates) it.copy(name = "${it.name} (${it.userId})") else it }
                        binding.userInput.setAdapter(
                            ArrayAdapter(requireContext(), android.R.layout.simple_list_item_1, users.map { it.name }),
                        )
                        binding.noUsersHint.isVisible = list.isEmpty()
                    }
                }
                launch {
                    viewModel.saved.collect {
                        Toast.makeText(requireContext(), R.string.saved_offline, Toast.LENGTH_SHORT).show()
                        parentFragmentManager.popBackStack()
                    }
                }
            }
        }
        updateSaveEnabled()
    }

    private fun selectedAction(): ActionType? = when (binding.actionToggle.checkedButtonId) {
        R.id.borrowButton -> ActionType.BORROW
        R.id.returnButton -> ActionType.RETURN
        else -> null
    }

    private fun updateSaveEnabled() {
        binding.saveButton.isEnabled = selectedAction() != null && selectedUser != null
    }

    private fun onSave() {
        val action = selectedAction() ?: return
        val user = selectedUser ?: run {
            binding.userInputLayout.error = getString(R.string.select_user_error)
            return
        }
        binding.saveButton.isEnabled = false
        viewModel.save(user.userId, action)
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }

    companion object {
        const val ARG_QR_ID = "qr_id"

        fun newInstance(qrId: String) = ItemActionFragment().apply {
            arguments = bundleOf(ARG_QR_ID to qrId)
        }
    }
}
